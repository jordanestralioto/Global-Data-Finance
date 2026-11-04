"""Serialize lock initialization and removal through kernel-owned handles."""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...macro_exceptions import ExtractionError
from .ownership import require_private_entry

WINDOWS_GUARD_NAME = '.globaldatafinance-publication.guard'


@contextmanager
def destination_guard(
    destination: Path, *, blocking: bool = False
) -> Iterator[None]:
    """Protect incomplete locks without relying on their JSON records.

    POSIX locks the destination directory itself. Windows retains one empty
    private guard file: unlinking it would let contenders lock different
    inodes. Closing the handle releases either platform's kernel lock.
    """
    descriptor = _open_guard(destination)
    try:
        try:
            _lock_descriptor(descriptor, blocking=blocking)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise ExtractionError(
                    str(destination),
                    'Destination transaction lock is being initialized '
                    'or recovered by another writer',
                ) from error
            raise
        yield
    finally:
        os.close(descriptor)


def _open_guard(destination: Path) -> int:
    if sys.platform != 'win32':
        return os.open(
            destination,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0),
        )
    path = destination / WINDOWS_GUARD_NAME
    if path.is_symlink():
        raise ExtractionError(str(path), 'Transaction guard cannot be a link')
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        checked = require_private_entry(path)
        opened = os.fstat(descriptor)
        if (checked.st_dev, checked.st_ino) != (opened.st_dev, opened.st_ino):
            raise ExtractionError(str(path), 'Transaction guard changed')
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _lock_descriptor(descriptor: int, *, blocking: bool) -> None:
    if sys.platform == 'win32':
        import msvcrt

        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        msvcrt.locking(descriptor, mode, 1)
    else:
        import fcntl

        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(descriptor, flags)
