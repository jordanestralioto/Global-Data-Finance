"""Discovery and selection for consumer validation scopes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.consumer_types import BoundaryError, Diagnostic
from harness.consumer_validators import (
    validate_agent_item,
    validate_skill_item,
    validate_workflow_item,
)

IGNORED_DIR_NAMES = {
    '__pycache__',
    '.git',
}


@dataclass(frozen=True)
class DiscoveredItem:
    name: str
    path: str
    file_path: Path
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            'name': self.name,
            'path': self.path,
            'sha256': self.sha256,
        }

    def validate(self, root: Path, scope_name: str) -> list[Diagnostic]:
        if scope_name == 'skills':
            return validate_skill_item(
                root, self.file_path, self.path, self.name
            )
        if scope_name == 'agents':
            return validate_agent_item(
                root, self.file_path, self.path, self.name
            )
        if scope_name == 'workflows':
            return validate_workflow_item(
                root, self.file_path, self.path, self.name
            )
        return []


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_confinement(root: Path, file_path: Path, scope_name: str) -> None:
    try:
        if not file_path.resolve().is_relative_to(root.resolve()):
            raise BoundaryError(
                f"discovered {scope_name} item '{file_path}' escapes repository root via symlink"
            )
    except OSError as exc:
        raise BoundaryError(
            f"discovered {scope_name} item '{file_path}' cannot be resolved safely"
        ) from exc


def discover_scope_items(
    root: Path, scope_name: str, scope_path_str: str
) -> list[DiscoveredItem]:
    scope_dir = root / scope_path_str
    if not scope_dir.exists():
        return []
    items: list[DiscoveredItem] = []
    if scope_name == 'skills':
        for skill_file in sorted(scope_dir.rglob('SKILL.md')):
            parts = skill_file.relative_to(scope_dir).parts
            if any(
                p in IGNORED_DIR_NAMES or p.startswith('.') for p in parts[:-1]
            ):
                continue
            _check_confinement(root, skill_file, scope_name)
            name = skill_file.relative_to(scope_dir).parent.as_posix()
            rel = skill_file.relative_to(root).as_posix()
            items.append(
                DiscoveredItem(
                    name=name,
                    path=rel,
                    file_path=skill_file,
                    sha256=_sha256_bytes(skill_file.read_bytes()),
                )
            )
    elif scope_name == 'agents':
        for agent_file in sorted(scope_dir.rglob('*.agent.md')):
            parts = agent_file.relative_to(scope_dir).parts
            if any(
                p in IGNORED_DIR_NAMES or p.startswith('.') for p in parts[:-1]
            ):
                continue
            _check_confinement(root, agent_file, scope_name)
            name = agent_file.relative_to(scope_dir).as_posix()
            rel = agent_file.relative_to(root).as_posix()
            items.append(
                DiscoveredItem(
                    name=name,
                    path=rel,
                    file_path=agent_file,
                    sha256=_sha256_bytes(agent_file.read_bytes()),
                )
            )
    elif scope_name == 'workflows':
        for wf_file in sorted(scope_dir.rglob('*.prompt.md')):
            parts = wf_file.relative_to(scope_dir).parts
            if any(
                p in IGNORED_DIR_NAMES or p.startswith('.') for p in parts[:-1]
            ):
                continue
            _check_confinement(root, wf_file, scope_name)
            name = wf_file.relative_to(scope_dir).as_posix()
            rel = wf_file.relative_to(root).as_posix()
            items.append(
                DiscoveredItem(
                    name=name,
                    path=rel,
                    file_path=wf_file,
                    sha256=_sha256_bytes(wf_file.read_bytes()),
                )
            )
    return items


def apply_scope_selection(
    scope_name: str,
    scope_def: dict[str, Any],
    discovered: list[DiscoveredItem],
) -> tuple[list[DiscoveredItem], list[DiscoveredItem]]:
    is_required = bool(scope_def.get('required', False))
    includes = scope_def.get('include')
    excludes = scope_def.get('exclude')

    has_non_empty_inc = includes is not None and len(includes) > 0
    has_non_empty_exc = excludes is not None and len(excludes) > 0

    if is_required:
        if has_non_empty_inc or has_non_empty_exc:
            raise BoundaryError(
                f"required scope '{scope_name}' cannot use include or exclude filters"
            )
        return discovered, []

    disc_map = {item.name: item for item in discovered}
    disc_names = set(disc_map)
    effective_names = set(disc_names)

    if includes is not None:
        if not includes:
            raise BoundaryError(
                f"filters in optional scope '{scope_name}' produces an empty selection"
            )
        if len(includes) != len(set(includes)):
            raise BoundaryError(
                f"include filter in scope '{scope_name}' contains duplicate names"
            )
        inc_set = set(includes)
        unknown_inc = inc_set - disc_names
        if unknown_inc:
            raise BoundaryError(
                f"unmatched include filter name in scope '{scope_name}': {sorted(unknown_inc)}"
            )
        effective_names &= inc_set

    if excludes is not None:
        if len(excludes) != len(set(excludes)):
            raise BoundaryError(
                f"exclude filter in scope '{scope_name}' contains duplicate names"
            )
        exc_set = set(excludes)
        unknown_exc = exc_set - disc_names
        if unknown_exc:
            raise BoundaryError(
                f"unmatched exclude filter name in scope '{scope_name}': {sorted(unknown_exc)}"
            )
        effective_names -= exc_set

    if includes is not None and excludes is not None:
        overlap = set(includes) & set(excludes)
        if overlap:
            raise BoundaryError(
                f"scope '{scope_name}' has overlapping names in include and exclude filters: {sorted(overlap)}"
            )

    if (includes is not None or excludes is not None) and not effective_names:
        raise BoundaryError(
            f"filters in optional scope '{scope_name}' produces an empty selection"
        )

    effective = [disc_map[n] for n in sorted(effective_names)]
    excluded = [
        item for item in discovered if item.name not in effective_names
    ]
    return effective, excluded
