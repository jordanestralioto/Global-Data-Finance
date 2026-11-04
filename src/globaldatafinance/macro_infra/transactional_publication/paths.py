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


def bind_artifact_destination(path: Path, destination_dir: Path) -> Path:
    """Bind an output name to its canonical parent without following links."""
    final = path.parent.resolve() / path.name
    if (
        not path.name
        or path.name == '..'
        or final == destination_dir.resolve()
    ):
        raise ExtractionError(
            str(destination_dir), f'Path must name an artifact below: {path}'
        )
    require_descendant(final.parent, destination_dir)
    return final


def validate_artifact_destination(path: Path, destination_dir: Path) -> Path:
    """Reject symbolic links before staging or replacing a bound output."""
    final = bind_artifact_destination(path, destination_dir)
    if final.is_symlink():
        raise ExtractionError(
            str(final), 'Artifact destination cannot be a symbolic link'
        )
    return final


def relative_to(path: Path, destination_dir: Path) -> str:
    """Serialize one verified path relative to the publication destination."""
    bound = bind_artifact_destination(path, destination_dir)
    return bound.relative_to(destination_dir.resolve()).as_posix()
