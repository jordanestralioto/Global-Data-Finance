"""Destination ownership, locking, and manifest recovery coordination."""

from __future__ import annotations

import contextlib
import os
import re
import socket
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil

from ...core.config import PathSafetySettings
from ...core.utils import normalize_destination_path
from ...macro_exceptions import (
    DiskFullError,
    ExtractionError,
    PathIsNotDirectoryError,
    PathPermissionError,
)
from .durability import sync_directory
from .locking import destination_guard
from .manifests import ManifestStore
from .ownership import read_private_json, require_private_entry
from .paths import require_descendant
from .publication import TransactionalPublication
from .types import (
    JOURNAL_NAME,
    LOCK_NAME,
    MANIFEST_PREFIX,
    ArtifactIntent,
    FileOperations,
    PublicationManifest,
)


class TransactionalPublisher:
    """Create durable publication transactions for one caller destination."""

    def __init__(
        self,
        destination_dir: str | Path,
        *,
        owner: str,
        source_path: str | None = None,
        operations: FileOperations | None = None,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> None:
        """Store a caller-owned destination and internal filesystem seam."""
        self._raw_destination = str(destination_dir)
        self.destination_dir = Path(destination_dir)
        self.owner = owner
        self.source_path = source_path or str(destination_dir)
        self.operations = operations or FileOperations()
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        self.lock_dir = self.destination_dir / LOCK_NAME
        self._manifest_store: ManifestStore | None = None
        self._transaction_id: str | None = None
        self._canonical_destination: Path | None = None

    def begin(
        self,
        *,
        source_descriptors: list[dict[str, str]] | None = None,
        required_bytes: int = 0,
    ) -> TransactionalPublication:
        """Recover stale state, lock the destination, and open staging."""
        self.validate_destination(required_bytes=required_bytes)
        self._manifest_store = ManifestStore(
            self.destination_dir, self.source_path, self.operations
        )
        self._acquire_lock()
        staging_dir: Path | None = None
        manifest_path: Path | None = None
        try:
            self._recover_pending()
            transaction_id = uuid4().hex
            staging_dir = self.operations.mkdtemp(
                f'{MANIFEST_PREFIX}{transaction_id}-', self.lock_dir
            ).resolve()
            self._require_descendant(staging_dir, self.destination_dir)
            manifest = PublicationManifest(
                transaction_id=transaction_id,
                owner=self.owner,
                destination_dir=self.destination_dir,
                staging_dir=staging_dir,
                created_at=datetime.now(UTC).isoformat(),
                source_descriptors=source_descriptors or [],
            )
            manifest_path = self._manifest_path(transaction_id)
            self._transaction_id = transaction_id
            self._write_lock(manifest_path)
            self._write_manifest(manifest, manifest_path)
            return TransactionalPublication(self, manifest, manifest_path)
        except Exception:
            if manifest_path is not None:
                with contextlib.suppress(OSError):
                    self._remove_file(manifest_path)
            if staging_dir is not None:
                with contextlib.suppress(OSError):
                    self._remove_tree(staging_dir)
            self._release_lock()
            raise

    def validate_destination(self, required_bytes: int = 0) -> None:
        """Validate the destination without opening transaction state."""
        if required_bytes < 0:
            raise ValueError('required_bytes cannot be negative')
        if self._canonical_destination is None:
            self._canonical_destination = normalize_destination_path(
                self._raw_destination,
                type_label='Destination path',
                empty_message='path cannot be empty or whitespace',
                allowed_unc_roots=self.allowed_unc_roots,
            )
        self.destination_dir = self._canonical_destination
        self.lock_dir = self.destination_dir / LOCK_NAME
        if not self.destination_dir.is_dir():
            raise PathIsNotDirectoryError(
                str(self.destination_dir), exists=self.destination_dir.exists()
            )
        if not os.access(self.destination_dir, os.W_OK):
            raise PathPermissionError(str(self.destination_dir))
        if required_bytes > self.operations.disk_free_bytes(
            self.destination_dir
        ):
            raise DiskFullError(str(self.destination_dir))

    def ensure_backup_space(self, artifacts: list[ArtifactIntent]) -> None:
        """Reserve enough free space for copy-based rollback backups.

        Hard links normally make backups nearly free, but they are not a
        portable guarantee. Checking the complete size of pre-existing outputs
        before commit keeps a copy fallback from consuming an old artifact
        after publication has started.
        """
        backup_bytes = sum(
            artifact.final_path.stat().st_size
            for artifact in artifacts
            if artifact.final_path.is_file()
        )
        free_bytes = self.operations.disk_free_bytes(self.destination_dir)
        if backup_bytes > free_bytes:
            raise DiskFullError(str(self.destination_dir))

    def _acquire_lock(self) -> None:
        with destination_guard(self.destination_dir):
            try:
                self.operations.mkdir(self.lock_dir)
            except FileExistsError:
                self._recover_stale_lock()
                self.operations.mkdir(self.lock_dir)
            try:
                self._write_lock(None)
            except BaseException:
                with contextlib.suppress(OSError):
                    self._remove_tree(self.lock_dir)
                raise

    def _recover_stale_lock(self) -> None:
        require_private_entry(self.lock_dir, directory=True)
        try:
            lock_record = self._read_lock()
        except ExtractionError as error:
            if not isinstance(error.__cause__, FileNotFoundError):
                raise
            self._recover_uninitialized_lock()
            return
        if lock_record.get('hostname') != socket.gethostname():
            raise ExtractionError(
                self.source_path,
                'Destination transaction lock belongs to another host',
            )
        pid = lock_record.get('pid')
        if not isinstance(pid, int) or pid <= 0:
            raise ExtractionError(
                self.source_path,
                'Destination transaction lock has no verifiable process id',
            )
        if self._pid_is_alive(pid):
            raise ExtractionError(
                self.source_path,
                f'Destination transaction lock is held by live PID {pid}',
            )
        self._recover_pending()
        self._remove_tree(self.lock_dir)

    def _recover_uninitialized_lock(self) -> None:
        """Reclaim only the reserved initial record under the held guard."""
        for entry in self.lock_dir.iterdir():
            if (
                re.fullmatch(r'owner\.json-[0-9a-f]{32}\.tmp', entry.name)
                is None
            ):
                raise ExtractionError(
                    self.source_path,
                    'Incomplete transaction lock contains unverifiable state',
                )
            require_private_entry(entry)
        self._remove_tree(self.lock_dir)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            return bool(psutil.Process(pid).is_running())
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied as error:
            raise ExtractionError(
                str(pid), 'Cannot verify existing transaction process safely'
            ) from error

    def _write_lock(self, manifest_path: Path | None) -> None:
        record = {
            'hostname': socket.gethostname(),
            'pid': os.getpid(),
            'transaction_id': self._transaction_id or '',
            'created_at': datetime.now(UTC).isoformat(),
            'manifest': (
                manifest_path.name if manifest_path is not None else ''
            ),
        }
        path = self.lock_dir / 'owner.json'
        self._store.write_json_atomically(path, record)

    def _read_lock(self) -> dict[str, Any]:
        return read_private_json(self.lock_dir / 'owner.json')

    def _recover_pending(self) -> None:
        for manifest_path in sorted(
            self.destination_dir.glob(f'{MANIFEST_PREFIX}*.json')
        ):
            self._recover_manifest(manifest_path)
        staging_dirs = [
            *self.destination_dir.glob(f'{MANIFEST_PREFIX}*-*'),
            *self.lock_dir.glob(f'{MANIFEST_PREFIX}*-*'),
        ]
        for staging_dir in sorted(staging_dirs):
            if (staging_dir / JOURNAL_NAME).exists():
                manifest = self._store.read_journal(staging_dir)
                self._recover_manifest(
                    self._manifest_path(manifest.transaction_id),
                    manifest=manifest,
                )

    def _recover_manifest(
        self,
        manifest_path: Path,
        *,
        manifest: PublicationManifest | None = None,
    ) -> None:
        if manifest is None:
            manifest = self._read_manifest(manifest_path)
        transaction = TransactionalPublication(self, manifest, manifest_path)
        if manifest.phase in {'OPEN', 'VALIDATED', 'ROLLED_BACK'}:
            transaction._cleanup_rolled_back()
            return
        if manifest.phase in {'BACKUPS_READY', 'PUBLISHING', 'ROLLING_BACK'}:
            errors = transaction._restore_published_artifacts()
            if errors:
                raise ExtractionError(
                    self.source_path,
                    'Recovery could not restore transaction at '
                    f'{manifest_path}: {"; ".join(errors)}',
                )
            manifest.phase = 'ROLLED_BACK'
            self._write_manifest(manifest, manifest_path)
            transaction._cleanup_rolled_back()
            return
        if manifest.phase in {'COMMITTED', 'CLEANUP_PENDING'}:
            transaction._cleanup_committed()
            return
        raise ExtractionError(
            self.source_path,
            f'Unsupported transaction manifest state: {manifest.phase}',
        )

    def _write_manifest(
        self, manifest: PublicationManifest, manifest_path: Path
    ) -> None:
        self._store.write(manifest, manifest_path)

    def _read_manifest(self, manifest_path: Path) -> PublicationManifest:
        return self._store.read(manifest_path)

    def _remove_file(self, path: Path) -> None:
        if path.exists():
            require_private_entry(path)
            self.operations.unlink(path)
            sync_directory(self.operations, path.parent)

    def _remove_tree(
        self,
        path: Path,
        *,
        expected_identity: tuple[int, int] | None = None,
    ) -> None:
        if path.exists():
            status = require_private_entry(path, directory=True)
            identity = expected_identity or (status.st_dev, status.st_ino)
            self.operations.rmtree(path, expected_identity=identity)
            sync_directory(self.operations, path.parent)

    def _release_lock(self) -> None:
        with destination_guard(self.destination_dir, blocking=True):
            if self.lock_dir.exists():
                self._remove_tree(self.lock_dir)
        self._transaction_id = None

    def _release_lock_for(self, transaction_id: str) -> None:
        """Release the lock only when this publisher owns that transaction."""
        if self._transaction_id == transaction_id:
            self._release_lock()

    def _manifest_path(self, transaction_id: str) -> Path:
        return self.destination_dir / f'{MANIFEST_PREFIX}{transaction_id}.json'

    @property
    def _store(self) -> ManifestStore:
        if self._manifest_store is None:
            raise RuntimeError(
                'Destination validation must precede publication'
            )
        return self._manifest_store

    @staticmethod
    def _require_descendant(path: Path, parent: Path) -> None:
        require_descendant(path, parent)
