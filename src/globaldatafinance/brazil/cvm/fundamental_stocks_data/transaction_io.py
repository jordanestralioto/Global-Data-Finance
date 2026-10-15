"""CVM transaction I/O rooted in the existing source destination lease."""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from ....macro_exceptions import SecurityError
from ....macro_infra.transactional_publication import FileOperations
from ....macro_infra.transactional_publication.cleanup import remove_owned_tree
from .destination_io import DestinationFileOperationsCVM


class CvmTransactionFileOperations(FileOperations):
    """Keep staged artifacts and replacements in opened directories."""

    def __init__(self, destination: DestinationFileOperationsCVM) -> None:
        """Reuse the parent lease and retain transaction directory handles."""
        self.destination = destination
        self._directories = {destination.snapshot.path: destination}
        self._children = ExitStack()

    def __enter__(self) -> CvmTransactionFileOperations:
        """Own child directory handles until the transaction ends."""
        return self

    def __exit__(self, *_exception: object) -> None:
        """Close every transaction child without closing the caller's lease."""
        self._children.close()

    def _directory(self, path: Path) -> DestinationFileOperationsCVM:
        parent = self._directories.get(path)
        if parent is not None:
            return parent
        if not path.is_relative_to(self.destination.snapshot.path) or (
            '..' in path.parts
        ):
            raise SecurityError(
                'CVM transaction path has no owned directory', path=str(path)
            )
        owner = self._directory(path.parent)
        directory = self._children.enter_context(
            owner.open_child_directory(path)
        )
        self._directories[path] = directory
        return directory

    def bound_path(self, path: Path) -> Path:
        """Give direct CSV and Parquet I/O a stable descriptor-backed path."""
        directory = self._directories.get(path)
        if directory is not None:
            return directory.bound_path(path)
        return self._directory(path.parent).bound_path(path)

    def mkdir(self, path: Path) -> None:
        """Create and retain a child through its owned parent directory."""
        self._directory(path.parent).mkdir(path, mode=0o700)
        self._directory(path)

    def mkdtemp(self, prefix: str, destination: Path) -> Path:
        """Create one transaction-private directory in the leased parent."""
        path = destination / f'{prefix}{uuid4().hex}'
        self.mkdir(path)
        return path

    def makedirs(self, path: Path) -> None:
        """Ensure a staged parent exists through its opened directory."""
        try:
            self._directory(path)
        except FileNotFoundError:
            self.makedirs(path.parent)
            self.mkdir(path)

    def link(self, source: Path, destination: Path) -> None:
        """Create backups between the already opened artifact parents."""
        source_parent = self._directory(source.parent)
        target_parent = self._directory(destination.parent)
        if (
            source_parent.descriptor is None
            or target_parent.descriptor is None
        ):
            super().link(source, destination)
        else:
            os.link(
                source.name,
                destination.name,
                src_dir_fd=source_parent.descriptor,
                dst_dir_fd=target_parent.descriptor,
                follow_symlinks=False,
            )

    def copy2(self, source: Path, destination: Path) -> None:
        """Copy rollback bytes through stable paths when linking fails."""
        super().copy2(self.bound_path(source), self.bound_path(destination))

    def replace(self, source: Path, destination: Path) -> None:
        """Publish or roll back artifacts relative to both owned parents."""
        self._directory(destination.parent).replace(
            source,
            destination,
            source_operations=self._directory(source.parent),
        )

    def unlink(self, path: Path) -> None:
        """Remove one transaction artifact within its opened parent."""
        self._directory(path.parent).unlink(path)

    def rmtree(
        self, path: Path, *, expected_identity: tuple[int, int]
    ) -> None:
        """Remove transaction state through its original parent descriptor."""
        parent = self._directory(path.parent)
        remove_owned_tree(
            path,
            expected_identity=expected_identity,
            parent_descriptor=parent.descriptor,
        )
        for directory in tuple(self._directories):
            if directory.is_relative_to(path):
                del self._directories[directory]

    def write_bytes(self, path: Path, payload: bytes) -> None:
        """Persist transaction records through the owned parent directory."""
        self._directory(path.parent).write_bytes(path, payload)

    def fsync_file(self, path: Path) -> None:
        """Flush artifact bytes through their opened parent directory."""
        self._directory(path.parent).fsync_file(path)

    def fsync_directory(self, path: Path) -> None:
        """Flush the original transaction directory descriptor."""
        self._directory(path).fsync_directory(path)

    def disk_free_bytes(self, path: Path) -> int:
        """Measure available storage on the leased filesystem."""
        directory = self._directory(path)
        if directory.descriptor is None:
            return super().disk_free_bytes(path)
        status = os.fstatvfs(directory.descriptor)
        return status.f_bavail * status.f_frsize
