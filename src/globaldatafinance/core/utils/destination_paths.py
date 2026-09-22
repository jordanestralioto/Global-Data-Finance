"""Shared destination normalization and creation for CVM and B3 owners."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from ...macro_exceptions import (
    InvalidDestinationPathError,
    PathCreationError,
    PathIsNotDirectoryError,
    PathPermissionError,
)
from .path_safety import assert_path_not_sensitive


def normalize_destination_path(
    path: str | Path,
    *,
    type_label: str,
    empty_message: str,
    allowed_unc_roots: Sequence[str] | None,
) -> Path:
    """Validate raw destination syntax and return a resolved safe path.

    Args:
        path: Caller-provided raw destination string or path.
        type_label: Human label used in the TypeError diagnostic.
        empty_message: Message used when path is empty or whitespace.
        allowed_unc_roots: Optional trusted UNC roots snapshot from the source
            owner. ``None`` uses the configured repository policy.

    Returns:
        An expanded, resolved, and safety-checked Path.

    Raises:
        TypeError: If path is neither a string nor a Path.
        InvalidDestinationPathError: If path is empty or whitespace.
        SecurityError: If path targets a sensitive system directory.
    """
    if not isinstance(path, (str, Path)):
        raise TypeError(
            f'{type_label} must be a string, got {type(path).__name__}'
        )
    raw_path = str(path)
    if not raw_path or raw_path.isspace():
        raise InvalidDestinationPathError(empty_message)
    normalized = Path(path).expanduser().resolve()
    assert_path_not_sensitive(
        normalized,
        raw_input=raw_path,
        allowed_unc_roots=allowed_unc_roots,
    )
    return normalized


def prepare_writable_destination(
    path: str | Path,
    *,
    type_label: str,
    empty_message: str,
    allowed_unc_roots: Sequence[str] | None,
) -> Path:
    """Normalize, validate, and ensure a writable destination directory.

    Args:
        path: Caller-provided raw destination string or path.
        type_label: Human label used in the TypeError diagnostic.
        empty_message: Message used when path is empty or whitespace.
        allowed_unc_roots: Trusted UNC roots snapshot from the source owner.

    Returns:
        A resolved, writable directory Path.

    Raises:
        TypeError: If path is neither a string nor a Path.
        InvalidDestinationPathError: If path is empty or whitespace.
        SecurityError: If path targets a sensitive system directory.
        PathIsNotDirectoryError: If the path exists but is not a directory.
        PathPermissionError: If the directory exists but is not writable,
            or if creation fails due to permissions.
        PathCreationError: If directory creation fails for other OS reasons.
    """
    normalized = normalize_destination_path(
        path,
        type_label=type_label,
        empty_message=empty_message,
        allowed_unc_roots=allowed_unc_roots,
    )
    if normalized.exists():
        if not normalized.is_dir():
            raise PathIsNotDirectoryError(
                str(normalized), exists=normalized.exists()
            )
        if not os.access(str(normalized), os.W_OK):
            raise PathPermissionError(str(normalized))
        return normalized
    try:
        normalized.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PathPermissionError(str(normalized)) from exc
    except OSError as exc:
        raise PathCreationError(str(normalized), str(exc)) from exc
    if not normalized.is_dir():
        raise PathIsNotDirectoryError(
            str(normalized), exists=normalized.exists()
        )
    if not os.access(str(normalized), os.W_OK):
        raise PathPermissionError(str(normalized))
    return normalized
