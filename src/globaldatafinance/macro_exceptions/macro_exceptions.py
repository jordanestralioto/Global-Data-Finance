"""Shared exception types for filesystem, network, and extraction failures."""

from typing import Any


class EmptyDirectoryError(Exception):
    """Indicate that a required directory contains no usable files."""

    def __init__(self, path: str):
        """Create an error for the empty directory path."""
        super().__init__(f'Directory is empty: {path!r}')


class InvalidDestinationPathError(ValueError):
    """Indicate that a destination path failed validation."""

    def __init__(self, reason: str):
        """Create an error with the path validation reason."""
        super().__init__(f'Invalid destination path: {reason}')


class PathIsNotDirectoryError(ValueError):
    """Indicate that a destination path is missing or not a directory."""

    def __init__(self, path: str, *, exists: bool | None = None):
        """Create an error for the invalid destination path."""
        if exists is False:
            message = f"Destination path does not exist: '{path}'."
        else:
            message = (
                f"Destination path must be a directory, but '{path}' is a "
                'file.'
            )
        super().__init__(message)


class PathPermissionError(OSError):
    """Indicate that a destination path is not writable."""

    def __init__(self, path: str):
        """Create an error for the unwritable destination path."""
        super().__init__(
            f'Permission denied: No write permission for destination path '
            f"'{path}'"
        )


class NetworkError(Exception):
    """Indicate a network failure while downloading a document."""

    def __init__(self, doc_name: str, message: str | None = None):
        """Create an error with the document and optional detail."""
        super().__init__(
            f"Network error while downloading '{doc_name}'. {message or ''}"
        )


class DownloadTimeoutError(Exception):
    """Indicate that a document download exceeded its timeout."""

    def __init__(self, doc_name: str, timeout: float | None = None):
        """Create an error with the document and optional timeout value."""
        msg = f"Timeout while downloading '{doc_name}'."
        if timeout:
            msg += f' Timeout: {timeout}s.'
        super().__init__(msg)


class ExtractionError(Exception):
    """Indicate a failure while extracting an input archive."""

    def __init__(self, path: str, message: str):
        """Create an error with the source path and failure detail."""
        self.path = path
        self.message = message
        super().__init__(f"Extraction error for '{path}': {message}")

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip across multiprocessing spawn pools."""
        return (self.__class__, (self.path, self.message))


class CorruptedZipError(ExtractionError):
    """Indicate that a ZIP input is malformed or corrupted."""

    def __init__(self, zip_path: str, message: str):
        """Create an error with the ZIP path and corruption detail."""
        self.raw_message = message
        super().__init__(zip_path, f'Corrupted ZIP: {message}')

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip across multiprocessing spawn pools."""
        return (self.__class__, (self.path, self.raw_message))


class DiskFullError(OSError):
    """Indicate that an output write cannot fit on the target filesystem."""

    def __init__(self, path: str):
        """Create an error for the output path that could not be written."""
        super().__init__(f"Insufficient disk space for saving '{path}'.")


class SecurityError(Exception):
    """Indicate that a path or operation violated a security boundary."""

    def __init__(self, message: str, path: str | None = None):
        """Create an error with a message and optional offending path."""
        if path:
            super().__init__(f"Security violation: {message} (path: '{path}')")
        else:
            super().__init__(f'Security violation: {message}')


class PathCreationError(OSError):
    """Indicate that a destination directory could not be created."""

    def __init__(self, path: str, reason: str | None = None):
        """Create an error with the path and optional OS reason."""
        msg = f"Failed to create directory '{path}'"
        if reason:
            msg += f': {reason}'
        super().__init__(msg)


class FileWriteError(OSError):
    """Indicate that writing a file chunk failed."""

    def __init__(self, path: str, reason: str | None = None):
        """Create an error with the path and optional OS reason."""
        msg = f"Failed to write chunk to '{path}'"
        if reason:
            msg += f': {reason}'
        super().__init__(msg)


class ParquetWriteError(OSError):
    """Indicate that writing a Parquet output failed."""

    def __init__(self, path: str, reason: str | None = None):
        """Create an error with the path and optional OS reason."""
        msg = f"Failed to write Parquet file '{path}'"
        if reason:
            msg += f': {reason}'
        super().__init__(msg)
