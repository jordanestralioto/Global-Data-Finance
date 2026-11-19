"""Confine mirror I/O to non-symlink paths below the repository root.

On platforms with directory descriptors, each parent is opened without
following links and subsequent operations use that descriptor. The portable
fallback rechecks the path and replaces files atomically; it protects against
repository-supplied links, but cannot exclude concurrent parent substitution.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path

DIRECTORY_DESCRIPTORS = bool(getattr(os, 'O_NOFOLLOW', 0)) and all(
    operation in os.supports_dir_fd
    for operation in (
        os.open,
        os.stat,
        os.mkdir,
        os.unlink,
        os.rename,
        os.readlink,
        os.symlink,
    )
)


class UnsafePath(Exception):
    """A mirror path escapes the root or traverses a symbolic link."""


def _parts(root: Path, path: Path) -> tuple[str, ...]:
    try:
        parts = path.absolute().relative_to(root.absolute()).parts
    except ValueError as exc:
        raise UnsafePath('mirror path is outside the repository root') from exc
    if not parts or '..' in parts:
        raise UnsafePath('mirror path escapes the repository root')
    return parts


def inspect(root: Path, path: Path) -> os.stat_result | None:
    """Check every existing component, including dangling symlinks.

    A regular file obstructing a parent is not a symlink collision. Leave its
    eventual write failure to the generator, after projection publication.
    """
    cursor = root
    metadata = None
    for part in _parts(root, path):
        cursor /= part
        try:
            metadata = cursor.lstat()
        except (FileNotFoundError, NotADirectoryError):
            return None
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafePath(f'symbolic link in mirror path: {cursor}')
    return metadata


def _at(path: Path, descriptor: int | None) -> Path | str:
    return path if descriptor is None else path.name


def _metadata(path: Path, descriptor: int | None) -> os.stat_result | None:
    try:
        metadata = os.stat(
            _at(path, descriptor), dir_fd=descriptor, follow_symlinks=False
        )
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        raise UnsafePath(f'symbolic link in mirror path: {path}')
    return metadata


def _open_directory(path: Path, descriptor: int | None) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        return os.open(_at(path, descriptor), flags, dir_fd=descriptor)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            _metadata(path, descriptor)
        raise


@contextmanager
def _parent(
    root: Path,
    path: Path,
    *,
    create: bool = False,
    allow_leaf_link: bool = False,
) -> Iterator[int | None]:
    _parts(root, path)
    checked = path.parent if allow_leaf_link else path
    if checked.absolute() != root.absolute():
        inspect(root, checked)
    if not DIRECTORY_DESCRIPTORS:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        if checked.absolute() != root.absolute():
            inspect(root, checked)
        yield None
        return
    with ExitStack() as stack:
        descriptor = _open_directory(root.resolve(), None)
        stack.callback(os.close, descriptor)
        cursor = root
        for part in _parts(root, path)[:-1]:
            cursor /= part
            try:
                child = _open_directory(cursor, descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                with suppress(FileExistsError):
                    os.mkdir(part, dir_fd=descriptor)
                child = _open_directory(cursor, descriptor)
            descriptor = child
            stack.callback(os.close, child)
        yield descriptor


def is_file(root: Path, path: Path) -> bool:
    """Inspect a mirror target without following file or parent links."""
    metadata = inspect(root, path)
    return metadata is not None and stat.S_ISREG(metadata.st_mode)


def read_text(root: Path, path: Path) -> str | None:
    """Read a regular file safely; absent or obstructed targets return None."""
    try:
        with _parent(root, path) as descriptor:
            metadata = _metadata(path, descriptor)
            if metadata is None or not stat.S_ISREG(metadata.st_mode):
                return None
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
            flags |= getattr(os, 'O_NONBLOCK', 0)
            try:
                opened = os.open(
                    _at(path, descriptor), flags, dir_fd=descriptor
                )
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise UnsafePath(
                        f'symbolic link in mirror path: {path}'
                    ) from exc
                raise
            with os.fdopen(opened, encoding='utf-8') as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return None
                return handle.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


def write_text(root: Path, path: Path, text: str) -> None:
    """Replace an entry atomically, retaining existing regular-file modes."""
    with _parent(root, path, create=True) as descriptor:
        metadata = _metadata(path, descriptor)
        temporary = path.with_name(f'.{path.name}.{secrets.token_hex(12)}.tmp')
        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        )
        opened = os.open(
            _at(temporary, descriptor), flags, 0o666, dir_fd=descriptor
        )
        try:
            with os.fdopen(opened, 'w', encoding='utf-8') as handle:
                if metadata is not None and stat.S_ISREG(metadata.st_mode):
                    mode = stat.S_IMODE(metadata.st_mode)
                    if hasattr(os, 'fchmod'):
                        os.fchmod(handle.fileno(), mode)
                    else:
                        os.chmod(temporary, mode)
                handle.write(text)
            inspect(root, path)
            _metadata(path, descriptor)
            os.replace(
                _at(temporary, descriptor),
                _at(path, descriptor),
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
        finally:
            with suppress(FileNotFoundError):
                os.unlink(_at(temporary, descriptor), dir_fd=descriptor)


def unlink(root: Path, path: Path) -> None:
    """Remove only a validated regular entry in the pinned parent directory."""
    with _parent(root, path) as descriptor:
        metadata = _metadata(path, descriptor)
        if metadata is not None and stat.S_ISREG(metadata.st_mode):
            os.unlink(_at(path, descriptor), dir_fd=descriptor)


def link_state(root: Path, path: Path) -> tuple[bool, Path | None]:
    """Inspect an intentional client link without following any parent link."""
    try:
        with _parent(root, path, allow_leaf_link=True) as descriptor:
            metadata = os.stat(
                _at(path, descriptor), dir_fd=descriptor, follow_symlinks=False
            )
            link = (
                Path(os.readlink(_at(path, descriptor), dir_fd=descriptor))
                if stat.S_ISLNK(metadata.st_mode)
                else None
            )
            return True, link
    except (FileNotFoundError, NotADirectoryError):
        return False, None


def create_link(
    root: Path, path: Path, target: Path, *, directory: bool
) -> None:
    """Create the final intended client link inside a validated parent."""
    with _parent(root, path, create=True, allow_leaf_link=True) as descriptor:
        os.symlink(
            target,
            _at(path, descriptor),
            target_is_directory=directory,
            dir_fd=descriptor,
        )


def remove_link(root: Path, path: Path, expected: Path) -> None:
    """Remove only the final exact generated client link in a safe parent."""
    with _parent(root, path, allow_leaf_link=True) as descriptor:
        if (
            Path(os.readlink(_at(path, descriptor), dir_fd=descriptor))
            != expected
        ):
            raise UnsafePath(f'client link changed since planning: {path}')
        os.unlink(_at(path, descriptor), dir_fd=descriptor)
