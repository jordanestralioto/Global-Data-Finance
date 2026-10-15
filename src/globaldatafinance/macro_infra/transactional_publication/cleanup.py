"""Remove verified transaction trees through their opened directory handles."""

from __future__ import annotations

import os
import shutil
import stat
from contextlib import ExitStack
from pathlib import Path

from ...macro_exceptions import ExtractionError


def remove_owned_tree(
    path: Path,
    *,
    expected_identity: tuple[int, int],
    parent_descriptor: int | None = None,
) -> None:
    """Delete private contents without traversing a substituted root name."""
    if os.open not in os.supports_dir_fd:
        _require_identity(path.lstat(), expected_identity, path)
        for child_path in sorted(
            path.iterdir(), key=lambda entry: entry.name == 'owner.json'
        ):
            if child_path.is_dir() and not child_path.is_symlink():
                shutil.rmtree(child_path)
            else:
                child_path.unlink()
        _require_identity(path.lstat(), expected_identity, path)
        path.rmdir()
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
    with ExitStack() as handles:
        if parent_descriptor is None:
            parent_descriptor = os.open(path.parent, flags)
            handles.callback(os.close, parent_descriptor)
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
        handles.callback(os.close, descriptor)
        _require_identity(os.fstat(descriptor), expected_identity, path)
        with os.scandir(descriptor) as children:
            ordered = sorted(
                children, key=lambda entry: entry.name == 'owner.json'
            )
            for child in ordered:
                if child.is_dir(follow_symlinks=False):
                    shutil.rmtree(child.name, dir_fd=descriptor)
                else:
                    os.unlink(child.name, dir_fd=descriptor)
        current = os.stat(
            path.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        _require_identity(current, expected_identity, path)
        os.rmdir(path.name, dir_fd=parent_descriptor)


def _require_identity(
    status: os.stat_result, expected: tuple[int, int], path: Path
) -> None:
    if (
        not stat.S_ISDIR(status.st_mode)
        or (
            status.st_dev,
            status.st_ino,
        )
        != expected
    ):
        raise ExtractionError(
            str(path), 'Recovery directory identity changed before cleanup'
        )
