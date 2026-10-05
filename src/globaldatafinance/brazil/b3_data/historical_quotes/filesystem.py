"""Filesystem validation helpers for B3 historical quotes."""

from collections.abc import Sequence
from pathlib import Path

from ....core import get_logger
from ....core.config import PathSafetySettings
from ....core.utils.destination_paths import (
    normalize_destination_path,
    prepare_writable_destination,
    validate_existing_writable_directory,
)
from ....macro_exceptions import (
    PathIsNotDirectoryError,
)
from .catalog import resolve_cotahist_sources

logger = get_logger(__name__)


class FileSystemServiceB3:
    """Service for file system operations.

    Uses centralized exceptions from macro_exceptions.
    Implements path traversal protection for security via the shared
    ``assert_path_not_sensitive`` helper.
    """

    def __init__(
        self,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> None:
        """Store an immutable trusted-UNC policy snapshot."""
        self._allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )

    def validate_directory_path(self, path: str) -> Path:
        """Validate that a path exists and is a directory."""
        logger.debug('Validating directory path', extra={'path': path})

        normalized_path = normalize_destination_path(
            path,
            type_label='Path',
            empty_message='Path cannot be empty or whitespace',
            allowed_unc_roots=self._allowed_unc_roots,
        )

        if not normalized_path.exists():
            raise PathIsNotDirectoryError(str(normalized_path), exists=False)

        if not normalized_path.is_dir():
            raise PathIsNotDirectoryError(str(normalized_path), exists=True)

        logger.debug(
            'Directory path validated successfully',
            extra={'normalized_path': str(normalized_path)},
        )

        return normalized_path

    def prepare_destination_path(self, path: str) -> Path:
        """Validate or create a writable extraction destination directory."""
        return prepare_writable_destination(
            path,
            type_label='Destination path',
            empty_message='path cannot be empty or whitespace',
            allowed_unc_roots=self._allowed_unc_roots,
        )

    def validate_destination_path(self, path: str) -> Path:
        """Validate and normalize a destination without creating it."""
        normalized = normalize_destination_path(
            path,
            type_label='Destination path',
            empty_message='path cannot be empty or whitespace',
            allowed_unc_roots=self._allowed_unc_roots,
        )
        validate_existing_writable_directory(normalized)
        return normalized

    def find_files_by_years(self, directory: Path, years: range) -> set[str]:
        """Return validated annual inputs selected by the canonical catalog.

        Both ZIP and TXT representations pass full source validation before
        an equivalent TXT can be ignored. Missing years contribute no paths;
        extraction reports coverage using the full catalog resolution.
        """
        if not years:
            return set()
        resolution = resolve_cotahist_sources(directory, expected_years=years)
        matching_files = {str(source.path) for source in resolution.sources}
        if resolution.ignored_duplicate_sources:
            logger.warning(
                'Equivalent COTAHIST TXT ignored after complete validation',
                extra={
                    'selected_files': sorted(matching_files),
                    'ignored_files': list(
                        resolution.ignored_duplicate_sources
                    ),
                },
            )
        return matching_files
