"""Deterministic evidence snapshots for isolated consumer validation."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from harness.consumer_types import ContractError
from harness.consumer_validation import verify_path_confinement
from harness.consumer_validation_evidence_schema import (
    serialize_canonical,
    validate_snapshot_document,
)
from harness.consumer_validation_snapshot import (
    SNAPSHOT_RELATIVE_PATH,
    snapshot_from_result,
)


class SnapshotWriteError(ContractError):
    """The deterministic snapshot could not be published atomically."""


def serialize_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Serialize a validated snapshot with exactly one final LF."""
    validate_snapshot_document(snapshot)
    return serialize_canonical(snapshot)


def snapshot_path(root: Path) -> Path:
    """Resolve the fixed snapshot target while enforcing root confinement."""
    return verify_path_confinement(
        root, SNAPSHOT_RELATIVE_PATH, 'snapshot path', must_exist=False
    )


def _new_parent_dirs(parent: Path) -> list[Path]:
    missing: list[Path] = []
    cursor = parent
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    created: list[Path] = []
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)
    return created


def _remove_empty_dirs(directories: list[Path]) -> None:
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except OSError:
            break


def write_snapshot(root: Path, snapshot: dict[str, Any]) -> bytes:
    """Atomically publish a deterministic snapshot beneath the Git root."""
    target = snapshot_path(root)
    payload = serialize_snapshot(snapshot)
    created: list[Path] = []
    temporary: Path | None = None
    try:
        created = _new_parent_dirs(target.parent)
        fd, name = tempfile.mkstemp(
            prefix='.snapshot.', suffix='.tmp', dir=target.parent
        )
        temporary = Path(name)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink()
        _remove_empty_dirs(created)
        raise SnapshotWriteError(
            f'cannot atomically publish {SNAPSHOT_RELATIVE_PATH}: {exc}'
        ) from exc
    return payload


def publish_snapshot(
    root: Path, request_data: dict[str, Any], result: dict[str, Any]
) -> bytes:
    """Build and atomically publish a snapshot for a passing result."""
    return write_snapshot(root, snapshot_from_result(request_data, result))
