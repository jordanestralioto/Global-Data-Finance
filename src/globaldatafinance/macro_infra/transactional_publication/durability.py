"""Durability primitives shared by transactional publication components."""

from __future__ import annotations

import errno
from pathlib import Path

from ...core import get_logger
from .types import FileOperations

logger = get_logger(__name__)


def sync_file(operations: FileOperations, path: Path) -> None:
    """Require file data to be durable before publication advances."""
    operations.fsync_file(path)


def sync_directory(operations: FileOperations, path: Path) -> None:
    """Sync directory metadata, tolerating only unsupported platforms."""
    try:
        operations.fsync_directory(path)
    except OSError as error:
        if error.errno not in {
            errno.EINVAL,
            errno.ENOTSUP,
            getattr(errno, 'EOPNOTSUPP', errno.ENOTSUP),
        }:
            raise
        logger.warning(
            'Directory fsync is unsupported for %s: %s', path, error
        )
