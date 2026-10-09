"""Small evidence helpers shared by isolated validation workers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from globaldatafinance.core.utils import assert_path_not_sensitive
from scripts.file_digests import sha256_file as sha256_file

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def emit_progress(message: str) -> None:
    """Flush human-readable progress without changing JSON stdout."""
    sys.stderr.write(f'[validation] {message}\n')
    sys.stderr.flush()


def failed_details(public_result: Any, message: str) -> dict[str, Any]:
    """Build the common failed-case payload without losing public output."""
    return {
        'status': 'failed',
        'message': message,
        'publicResult': public_result,
        'published': True,
    }


def is_external_message(message: str) -> bool:
    """Recognize network-shaped failures returned by the public CVM result."""
    lowered = message.casefold()
    return any(
        marker in lowered
        for marker in (
            'network',
            'timeout',
            'connection',
            'dns',
            'name resolution',
            'temporarily unavailable',
        )
    )


def temporary_paths(root: Path) -> list[str]:
    """List known staging, recovery, and temporary artifacts below a root."""
    if not root.exists():
        return []
    markers = ('temp', 'tmp', 'staging', 'recovery', 'preflight')
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob('*')
        if any(marker in path.name.casefold() for marker in markers)
    )


def validate_external_directory(raw_input: str, label: str) -> Path:
    """Normalize and validate one caller-owned directory before any write."""
    if not raw_input or raw_input.isspace():
        raise ValueError(f'{label} cannot be empty or whitespace')
    normalized_path = Path(raw_input).expanduser().resolve()
    assert_path_not_sensitive(normalized_path, raw_input=raw_input)
    _require_external_path(normalized_path, label)
    if normalized_path.exists() and not normalized_path.is_dir():
        raise ValueError(f'{label} must be a directory: {normalized_path}')
    return normalized_path


def _require_external_path(path: Path, label: str) -> None:
    """Reject a destination located inside the repository checkout."""
    try:
        path.relative_to(_REPOSITORY_ROOT)
    except ValueError:
        return
    raise ValueError(f'{label} must be outside the repository: {path}')
