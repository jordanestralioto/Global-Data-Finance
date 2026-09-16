"""Filesystem seams and serializable facts for transactional publication."""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_PREFIX = '.globaldatafinance-transaction-'
LOCK_NAME = '.globaldatafinance-transaction.lock'
PHASES = frozenset(
    {
        'OPEN',
        'VALIDATED',
        'BACKUPS_READY',
        'PUBLISHING',
        'COMMITTED',
        'CLEANUP_PENDING',
        'ROLLING_BACK',
        'ROLLED_BACK',
    }
)


class FileOperations:
    """Filesystem seam for durable publication and fault-injection tests."""

    def mkdir(self, path: Path) -> None:
        """Create one directory atomically."""
        path.mkdir()

    def mkdtemp(self, prefix: str, destination: Path) -> Path:
        """Create a same-filesystem staging directory."""
        return Path(tempfile.mkdtemp(prefix=prefix, dir=destination))

    def link(self, source: Path, destination: Path) -> None:
        """Create a hard-link backup."""
        os.link(source, destination)

    def copy2(self, source: Path, destination: Path) -> None:
        """Copy a backup when hard links are unavailable."""
        shutil.copy2(source, destination)

    def replace(self, source: Path, destination: Path) -> None:
        """Atomically replace a destination path."""
        source.replace(destination)

    def unlink(self, path: Path) -> None:
        """Remove one file."""
        path.unlink()

    def rmtree(self, path: Path) -> None:
        """Remove a transaction-only directory."""
        shutil.rmtree(path)

    def write_bytes(self, path: Path, payload: bytes) -> None:
        """Write one manifest candidate."""
        if path.is_symlink():
            raise OSError(f'Refusing to write through symlink: {path}')
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        no_follow = getattr(os, 'O_NOFOLLOW', 0)
        if no_follow:
            flags |= no_follow
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(payload)
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(descriptor)
            raise

    def fsync_file(self, path: Path) -> None:
        """Flush file bytes and metadata."""
        with path.open('rb') as handle:
            os.fsync(handle.fileno())

    def fsync_directory(self, path: Path) -> None:
        """Flush directory metadata where the platform permits it."""
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def disk_free_bytes(self, path: Path) -> int:
        """Return free bytes in the destination filesystem."""
        return shutil.disk_usage(path).free


@dataclass
class ArtifactIntent:
    """One staged artifact and the final path it can safely replace."""

    final_path: Path
    staged_path: Path
    expected_rows: int
    schema_fingerprint: str
    backup_path: Path | None = None
    existed_before: bool = False
    publishing: bool = False
    published: bool = False


@dataclass
class PublicationManifest:
    """Serializable recovery record for one publication transaction."""

    transaction_id: str
    owner: str
    destination_dir: Path
    staging_dir: Path
    created_at: str
    artifacts: list[ArtifactIntent] = field(default_factory=list)
    source_descriptors: list[dict[str, str]] = field(default_factory=list)
    phase: str = 'OPEN'
    version: int = 1
