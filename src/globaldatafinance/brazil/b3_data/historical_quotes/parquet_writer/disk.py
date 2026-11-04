"""Disk-capacity validation used before B3 Parquet writes."""

import shutil
from pathlib import Path

from .....core import get_logger
from .....macro_exceptions import DiskFullError

logger = get_logger(__name__)


def check_disk_space(
    path: Path, estimated_size_mb: float, min_free_space_mb: int
) -> None:
    """Raise when the destination volume lacks the requested free space."""
    stat = shutil.disk_usage(path.parent)
    free_space_mb = stat.free / 1024 / 1024
    required_space_mb = estimated_size_mb + min_free_space_mb

    if free_space_mb < required_space_mb:
        logger.error(
            'Insufficient disk space',
            extra={
                'free_space_mb': f'{free_space_mb:.2f}',
                'required_space_mb': f'{required_space_mb:.2f}',
                'path': str(path),
            },
        )
        raise DiskFullError(str(path))

    logger.debug(
        'Disk space check passed',
        extra={
            'free_space_mb': f'{free_space_mb:.2f}',
            'required_space_mb': f'{required_space_mb:.2f}',
        },
    )
