"""Read OpenSpec manifests and enumerate active and archived changes."""

from __future__ import annotations

import re
from pathlib import Path

NON_CHANGE_DIRS = frozenset({'archive', 'paused'})
ARCHIVED_CHANGE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}-(.+)$')


def iter_change_dirs(changes_root: Path) -> list[Path]:
    if not changes_root.is_dir():
        return []
    return sorted(
        path
        for path in changes_root.iterdir()
        if path.is_dir() and path.name not in NON_CHANGE_DIRS
    )


def iter_decision_change_dirs(changes_root: Path) -> list[Path]:
    """Return active and archived decision owners.

    Archive is terminal lifecycle state, not deletion from the ownership
    registry.  Paused changes remain excluded because they are not terminal.
    """
    result = iter_change_dirs(changes_root)
    archive_root = changes_root / 'archive'
    if archive_root.is_dir():
        result.extend(
            path for path in sorted(archive_root.iterdir()) if path.is_dir()
        )
    return result


def logical_change_name(change_dir: Path) -> str:
    if change_dir.parent.name != 'archive':
        return change_dir.name
    match = ARCHIVED_CHANGE_RE.fullmatch(change_dir.name)
    return match.group(1) if match else change_dir.name


def _manifest_value(raw: str) -> object:
    value = raw.strip()
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [
            item.strip().strip('"\'')
            for item in inner.split(',')
            if item.strip()
        ]
    return value.strip('"\'')


def load_change_manifest(change_dir: Path) -> dict[str, object]:
    """Read the small YAML subset used by a change manifest."""
    path = change_dir / '.openspec.yaml'
    if not path.is_file():
        return {}
    manifest: dict[str, object] = {}
    nested: dict[str, object] | None = None
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith('#'):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        key, separator, raw_value = stripped.partition(':')
        if not separator:
            continue
        if indent == 0:
            if raw_value.strip():
                manifest[key] = _manifest_value(raw_value)
                nested = None
            else:
                nested = {}
                manifest[key] = nested
        elif indent == 2 and nested is not None:
            nested[key] = _manifest_value(raw_value)
    return manifest
