"""Processing mode and extraction configuration validation."""

import os
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath

from .errors import InvalidOutputFilename, InvalidProcessingMode


class ProcessingModeEnumB3(StrEnum):
    """Supported extraction modes selected by callers."""

    FAST = 'fast'
    SLOW = 'slow'


class ExtractionConfigServiceB3:
    """Domain service for validating extraction configuration parameters."""

    @staticmethod
    def validate_processing_mode(mode: str) -> str:
        """Validate the processing mode."""
        if not isinstance(mode, str):
            raise TypeError(
                f'processing_mode must be a string, got {type(mode).__name__}'
            )

        try:
            valid_mode: str = ProcessingModeEnumB3(mode.lower()).value
            return valid_mode
        except ValueError as exc:
            valid_modes = [m.value for m in ProcessingModeEnumB3]
            raise InvalidProcessingMode(mode, valid_modes) from exc

    @staticmethod
    def validate_output_filename(filename: str) -> str:
        r"""Validate the output filename.

        Accepts only a bare basename. The following are rejected with
        :class:`InvalidOutputFilename` because they enable path traversal
        outside the validated destination:

        - Strings containing ``/`` or ``\`` (path separators).
        - Any ``..`` traversal segment.
        - Absolute paths (POSIX leading ``/`` or Windows drive letter).
        - Empty / whitespace-only strings.

        If the basename does not end in ``.parquet`` (case-insensitive),
        the suffix is appended automatically.
        """
        if not isinstance(filename, str):
            raise TypeError(
                f'output_filename must be a string, '
                f'got {type(filename).__name__}'
            )

        if not filename.strip():
            raise InvalidOutputFilename(
                'Filename cannot be empty or whitespace'
            )

        if '/' in filename or '\\' in filename or os.sep in filename:
            raise InvalidOutputFilename(
                f'output_filename must be a basename '
                f'(no path separators), got {filename!r}'
            )

        posix_view = PurePosixPath(filename)
        if '..' in posix_view.parts:
            raise InvalidOutputFilename(
                f'output_filename must not contain traversal '
                f'segments, got {filename!r}'
            )

        if posix_view.is_absolute():
            raise InvalidOutputFilename(
                f'output_filename must not be an absolute path, '
                f'got {filename!r}'
            )

        if PureWindowsPath(filename).drive:
            raise InvalidOutputFilename(
                f'output_filename must not contain a Windows drive '
                f'letter, got {filename!r}'
            )

        if not filename.lower().endswith('.parquet'):
            return f'{filename}.parquet'

        return filename
