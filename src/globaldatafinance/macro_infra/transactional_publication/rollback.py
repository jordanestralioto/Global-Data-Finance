"""Restore only artifacts owned by the interrupted transaction."""

from __future__ import annotations

from ...macro_exceptions import ExtractionError
from .ownership import artifact_identity, artifact_sha256
from .types import ArtifactIntent, FileOperations


def restore_artifact(item: ArtifactIntent, operations: FileOperations) -> None:
    """Preserve a caller's later output instead of trusting a path and flag."""
    try:
        current = artifact_identity(item.final_path)
    except FileNotFoundError:
        current = None
    digest = artifact_sha256(item.final_path) if current is not None else None
    if current is not None and (
        (current == item.original_identity and digest == item.original_sha256)
        or (current == item.backup_identity and digest == item.backup_sha256)
    ):
        return
    if current is None and not item.existed_before:
        return
    if (
        current is None
        or current != item.publication_identity
        or digest != item.publication_sha256
    ):
        raise ExtractionError(
            str(item.final_path),
            'Recovery preserves an output changed outside this transaction',
        )
    if item.backup_path is not None:
        if (
            artifact_identity(item.backup_path) != item.backup_identity
            or artifact_sha256(item.backup_path) != item.backup_sha256
        ):
            raise ExtractionError(
                str(item.backup_path), 'Recovery backup identity changed'
            )
        operations.replace(item.backup_path, item.final_path)
    else:
        operations.unlink(item.final_path)
