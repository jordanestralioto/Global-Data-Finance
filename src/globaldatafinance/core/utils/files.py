"""Filesystem helpers shared across the library."""

from __future__ import annotations

from pathlib import Path

from ..logging_config import get_logger

logger = get_logger(__name__)


def remove_file(filepath: str | Path, log_on_error: bool = True) -> None:
    """Remove a file from disk safely.

    Removes any file from disk, with optional logging on errors. Handles
    missing files gracefully.

    Args:
        filepath: Path to the file to remove.
        log_on_error: If True, logs warnings when file deletion fails.

    Example:
        >>> from globaldatafinance.core.utils.files import remove_file
        >>>
        >>> remove_file('/path/to/file.zip')
    """
    try:
        path_obj = Path(filepath)
        if path_obj.exists():
            path_obj.unlink()
            logger.debug('Removed file: %s', filepath)
    except OSError:
        if log_on_error:
            logger.warning('Failed to remove file %s', filepath, exc_info=True)
