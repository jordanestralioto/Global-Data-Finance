"""Path-boundary helpers for durable publication state."""

from __future__ import annotations

from pathlib import Path

from ...macro_exceptions import ExtractionError


def require_descendant(path: Path, parent: Path) -> None:
    """Reject paths that escape the caller-owned publication directory."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as error:
        raise ExtractionError(
            str(parent), f'Path escapes transaction boundary: {path}'
        ) from error


def require_strict_descendant(path: Path, parent: Path) -> None:
    """Reject the parent itself as well as paths outside its boundary."""
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    if resolved_path == resolved_parent:
        raise ExtractionError(
            str(parent), f'Path must name an artifact below: {resolved_path}'
        )
    require_descendant(resolved_path, resolved_parent)


def relative_to(path: Path, destination_dir: Path) -> str:
    """Serialize one verified path relative to the publication destination."""
    require_descendant(path.resolve(), destination_dir)
    return path.resolve().relative_to(destination_dir).as_posix()
