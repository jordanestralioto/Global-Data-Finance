"""Destination ownership, locking, and manifest recovery coordination."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import string
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.config import PathSafetySettings
from ...core.utils import normalize_destination_path
from ...macro_exceptions import (
    DiskFullError,
    ExtractionError,
    PathIsNotDirectoryError,
    PathPermissionError,
)
from .durability import sync_directory
from .manifests import ManifestStore
from .paths import require_descendant
from .publication import TransactionalPublication
from .types import (
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
                f'{MANIFEST_PREFIX}{transaction_id}-', self.destination_dir
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
        staged_bytes = sum(
            artifact.staged_path.stat().st_size
            for artifact in artifacts
            if artifact.staged_path.is_file()
        )
        backup_bytes = sum(
            artifact.final_path.stat().st_size
            for artifact in artifacts
            if artifact.final_path.is_file()
        )
        free_bytes = self.operations.disk_free_bytes(self.destination_dir)
        if staged_bytes + backup_bytes > free_bytes:
            raise DiskFullError(str(self.destination_dir))

    def _acquire_lock(self) -> None:
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
        lock_record = self._read_lock()
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
        manifest_name = lock_record.get('manifest')
        if isinstance(manifest_name, str) and manifest_name:
            manifest_path = (self.destination_dir / manifest_name).resolve()
            self._require_descendant(manifest_path, self.destination_dir)
            if manifest_path.is_file():
                self._recover_manifest(manifest_path)
            else:
                self._recover_orphan_transaction(lock_record)
        else:
            self._recover_orphan_transaction(lock_record)
        self._remove_tree(self.lock_dir)

    def _recover_orphan_transaction(self, lock_record: dict[str, Any]) -> None:
        """Remove only derived state left before a manifest became durable."""
        transaction_id = lock_record.get('transaction_id', '')
        if not isinstance(transaction_id, str):
            raise ExtractionError(
                self.source_path,
                'Stale transaction lock has an invalid transaction id',
            )
        if transaction_id and (
            len(transaction_id) != 32
            or any(
                character not in string.hexdigits
                for character in transaction_id
            )
        ):
            raise ExtractionError(
                self.source_path,
                'Stale transaction lock has an unverifiable transaction id',
            )

        if transaction_id:
            candidates = self.destination_dir.glob(
                f'{MANIFEST_PREFIX}{transaction_id}-*'
            )
        else:
            protected = {
                self._read_manifest(path).staging_dir.resolve()
                for path in self.destination_dir.glob(
                    f'{MANIFEST_PREFIX}*.json'
                )
            }
            candidates = (
                path
                for path in self.destination_dir.glob(f'{MANIFEST_PREFIX}*-*')
                if path.resolve() not in protected
            )

        for candidate in candidates:
            self._require_descendant(candidate.resolve(), self.destination_dir)
            if candidate.is_dir():
                self._remove_tree(candidate)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError as error:
            raise ExtractionError(
                str(pid), 'Cannot verify existing transaction process safely'
            ) from error
        return True

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
        path = self.lock_dir / 'owner.json'
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise ExtractionError(
                self.source_path,
                f'Cannot read destination transaction lock: {error}',
            ) from error
        if not isinstance(payload, dict):
            raise ExtractionError(
                self.source_path, 'Destination transaction lock is malformed'
            )
        return payload

    def _recover_pending(self) -> None:
        for manifest_path in sorted(
            self.destination_dir.glob(f'{MANIFEST_PREFIX}*.json')
        ):
            self._recover_manifest(manifest_path)

    def _recover_manifest(self, manifest_path: Path) -> None:
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
            self.operations.unlink(path)
            sync_directory(self.operations, path.parent)

    def _remove_tree(self, path: Path) -> None:
        if path.exists():
            self.operations.rmtree(path)
            sync_directory(self.operations, path.parent)

    def _release_lock(self) -> None:
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
