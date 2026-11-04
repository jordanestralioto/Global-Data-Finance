"""Verify private filesystem authority before reading recovery state."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from ...macro_exceptions import ExtractionError


def require_private_entry(
    path: Path, *, directory: bool = False
) -> os.stat_result:
    """Reject aliases, foreign owners and shared transaction state."""
    status = path.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(status.st_mode):
        raise ExtractionError(str(path), 'Recovery state has an unsafe type')
    if hasattr(os, 'geteuid') and (
        status.st_uid != os.geteuid() or status.st_mode & 0o077
    ):
        raise ExtractionError(
            str(path), 'Recovery state requires private filesystem ownership'
        )
    if not directory and status.st_nlink != 1:
        raise ExtractionError(
            str(path), 'Recovery state cannot be hard linked'
        )
    return status


def read_private_json(path: Path) -> dict[str, Any]:
    """Read the checked inode without following a replacement symlink."""
    try:
        checked = require_private_entry(path)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'r', encoding='utf-8') as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (
                checked.st_dev,
                checked.st_ino,
            ):
                raise ExtractionError(str(path), 'Recovery state changed')
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        raise ExtractionError(
            str(path), f'Cannot read private recovery state: {error}'
        ) from error
    if not isinstance(payload, dict):
        raise ExtractionError(str(path), 'Recovery state is malformed')
    return payload


def directory_identity(path: Path) -> list[int]:
    """Bind a journal to the directory in which it was created."""
    status = path.stat(follow_symlinks=False)
    return [status.st_dev, status.st_ino]


def artifact_identity(path: Path) -> list[int]:
    """Identify regular artifact bytes without following a final alias."""
    status = path.lstat()
    if not stat.S_ISREG(status.st_mode):
        raise ExtractionError(
            str(path), 'Artifact identity requires a regular file'
        )
    return _artifact_identity(status)


def _artifact_identity(status: os.stat_result) -> list[int]:
    return [status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns]


def artifact_sha256(path: Path) -> str:
    """Verify artifact bytes without accepting aliases or mid-read edits."""
    expected = artifact_identity(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if _artifact_identity(before) != expected:
            raise ExtractionError(
                str(path), 'Artifact changed before verification'
            )
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        after = os.fstat(handle.fileno())
        if (
            _artifact_identity(before) != _artifact_identity(after)
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ExtractionError(
                str(path), 'Artifact changed during verification'
            )
    return digest
