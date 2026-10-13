"""CVM directory identities and descriptor-bound filesystem operations."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ....core import get_logger
from ....macro_exceptions import SecurityError
from ....macro_infra.transactional_publication import FileOperations

logger = get_logger(__name__)


@dataclass(frozen=True)
class DownloadDestinationSnapshot:
    """Bind a download to its validated parent directory identity."""

    path: Path
    identity: tuple[int, int] | None


def capture_download_destination(parent: Path) -> DownloadDestinationSnapshot:
    """Record the directory before starting asynchronous download work."""
    resolved = parent.resolve()
    try:
        status = resolved.stat()
    except FileNotFoundError:
        identity = None
    else:
        identity = (status.st_dev, status.st_ino)
    return DownloadDestinationSnapshot(resolved, identity)


def assert_download_destination_unchanged(
    destination: Path, snapshot: DownloadDestinationSnapshot
) -> None:
    """Reject a redirected or replaced directory before publication."""
    status = destination.stat()
    identity = (status.st_dev, status.st_ino)
    if destination != snapshot.path or (
        snapshot.identity is not None and identity != snapshot.identity
    ):
        raise SecurityError(
            'CVM destination changed after validation', path=str(snapshot.path)
        )


def _supports_directory_descriptors() -> bool:
    return all(
        operation in os.supports_dir_fd
        for operation in (os.open, os.mkdir, os.unlink, os.rmdir, os.rename)
    ) and bool(getattr(os, 'O_DIRECTORY', 0))


class DestinationFileOperationsCVM(FileOperations):
    """Keep ZIP and lease mutations within one opened directory."""

    def __init__(
        self, snapshot: DownloadDestinationSnapshot, descriptor: int | None
    ) -> None:
        """Use descriptor-relative operations where the OS supports them."""
        self.snapshot = snapshot
        self.descriptor = descriptor

    def _basename(self, path: Path) -> str:
        if path.parent != self.snapshot.path:
            raise SecurityError(
                'CVM operation escapes its opened destination', path=str(path)
            )
        if self.descriptor is None:
            assert_download_destination_unchanged(
                self.snapshot.path.resolve(), self.snapshot
            )
        return path.name

    def mkdir(self, path: Path, *, mode: int = 0o777) -> None:
        """Create a child within the opened parent."""
        name = self._basename(path)
        if self.descriptor is None:
            path.mkdir(mode=mode)
        else:
            os.mkdir(name, mode=mode, dir_fd=self.descriptor)

    def replace(
        self,
        source: Path,
        destination: Path,
        *,
        source_operations: DestinationFileOperationsCVM | None = None,
    ) -> None:
        """Promote one child without resolving its parent pathname again."""
        source_parent = source_operations or self
        source_name = source_parent._basename(source)
        destination_name = self._basename(destination)
        if self.descriptor is None or source_parent.descriptor is None:
            super().replace(source, destination)
        else:
            os.replace(
                source_name,
                destination_name,
                src_dir_fd=source_parent.descriptor,
                dst_dir_fd=self.descriptor,
            )

    def unlink(self, path: Path) -> None:
        """Remove a child from the opened parent."""
        name = self._basename(path)
        if self.descriptor is None:
            super().unlink(path)
        else:
            os.unlink(name, dir_fd=self.descriptor)

    def rmdir(self, path: Path) -> None:
        """Remove an empty child directory within the opened parent."""
        name = self._basename(path)
        if self.descriptor is None:
            path.rmdir()
        else:
            os.rmdir(name, dir_fd=self.descriptor)

    def write_bytes(
        self, path: Path, payload: bytes, *, exclusive: bool = False
    ) -> None:
        """Write metadata within the opened parent without following links."""
        name = self._basename(path)
        if self.descriptor is None:
            if exclusive:
                with path.open('xb') as handle:
                    handle.write(payload)
            else:
                super().write_bytes(path, payload)
            return
        flags = os.O_WRONLY | os.O_CREAT
        flags |= os.O_EXCL if exclusive else os.O_TRUNC
        flags |= getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(name, flags, 0o600, dir_fd=self.descriptor)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)

    def fsync_file(self, path: Path) -> None:
        """Flush a child opened relative to the owned directory descriptor."""
        name = self._basename(path)
        if self.descriptor is None:
            super().fsync_file(path)
            return
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(name, flags, dir_fd=self.descriptor)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def fsync_directory(self, path: Path) -> None:
        """Flush the opened directory rather than its mutable pathname."""
        if path != self.snapshot.path:
            raise SecurityError('CVM directory sync escapes its destination')
        if self.descriptor is None:
            super().fsync_directory(path)
        else:
            os.fsync(self.descriptor)

    def bound_path(self, path: Path) -> Path:
        """Address file readers and writers through the held directory."""
        name = None if path == self.snapshot.path else self._basename(path)
        if self.descriptor is not None:
            for base in (Path('/proc/self/fd'), Path('/dev/fd')):
                opened = base / str(self.descriptor)
                if opened.is_dir():
                    return opened if name is None else opened / name
            raise SecurityError(
                'CVM descriptor-backed file paths are unavailable',
                path=str(path),
            )
        assert_download_destination_unchanged(
            self.snapshot.path.resolve(), self.snapshot
        )
        return path

    @contextmanager
    def open_child_directory(
        self, path: Path
    ) -> Iterator[DestinationFileOperationsCVM]:
        """Open a lease directory through its already opened parent."""
        name = self._basename(path)
        if self.descriptor is None:
            with open_download_destination(
                capture_download_destination(path)
            ) as child:
                yield child
            return
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(name, flags, dir_fd=self.descriptor)
        try:
            status = os.fstat(descriptor)
            snapshot = DownloadDestinationSnapshot(
                path, (status.st_dev, status.st_ino)
            )
            yield DestinationFileOperationsCVM(snapshot, descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def open_download_destination(
    snapshot: DownloadDestinationSnapshot,
) -> Iterator[DestinationFileOperationsCVM]:
    """Open and verify the original directory before any child mutation."""
    assert_download_destination_unchanged(snapshot.path.resolve(), snapshot)
    if not _supports_directory_descriptors():
        yield DestinationFileOperationsCVM(snapshot, None)
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(snapshot.path, flags)
    try:
        status = os.fstat(descriptor)
        if snapshot.identity is not None and snapshot.identity != (
            status.st_dev,
            status.st_ino,
        ):
            raise SecurityError('CVM destination changed while opening it')
        yield DestinationFileOperationsCVM(snapshot, descriptor)
    finally:
        os.close(descriptor)


def remove_owned_staging_file(
    filepath: str, *, destination: DownloadDestinationSnapshot
) -> None:
    """Preserve staging when the original directory cannot be confirmed."""
    try:
        with open_download_destination(destination) as operations:
            try:
                operations.unlink(Path(filepath))
            except FileNotFoundError:
                return
    except (OSError, RuntimeError, SecurityError):
        logger.warning(
            'Preserved staging file because its destination cannot be '
            'confirmed: %s',
            filepath,
            exc_info=True,
        )
