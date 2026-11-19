"""Structured outcomes shared by the mirror generators."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MirrorSync:
    """Repository-relative entries a sync found stale, rewrote or refused."""

    stale: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    unsafe_paths: dict[str, str] = field(default_factory=dict)

    def extend(self, other: MirrorSync) -> None:
        self.stale.extend(other.stale)
        self.updated.extend(other.updated)
        self.conflicts.extend(other.conflicts)
        self.unsafe_paths.update(other.unsafe_paths)

    def status(self, *, check: bool) -> str:
        if self.unsafe_paths:
            return 'unsafe'
        if self.conflicts:
            return 'conflict'
        if not self.stale:
            return 'ok'
        return 'stale' if check else 'updated'

    def exit_code(self, *, check: bool) -> int:
        return int(
            bool(self.unsafe_paths or self.conflicts or (check and self.stale))
        )


def report(result: MirrorSync, *, check: bool, **fields: Any) -> str:
    """Render the JSON payload every mirror generator prints."""
    return json.dumps(
        {
            'status': result.status(check=check),
            **fields,
            'stale': result.stale,
            'updated': result.updated,
            'conflicts': result.conflicts,
            'unsafePaths': result.unsafe_paths,
        },
        ensure_ascii=False,
        indent=2,
    )


def conflict_message(result: MirrorSync) -> str:
    """Explain ownership conflicts separately from unsafe filesystem paths."""
    return ''.join(
        f'refused {item}: it holds content the harness did not generate '
        'and Git cannot restore it; commit or move it, then rerun '
        'harness-sync\n'
        for item in result.conflicts
    ) + ''.join(
        f'refused unsafe mirror path {item}: {reason}\n'
        for item, reason in result.unsafe_paths.items()
    )
