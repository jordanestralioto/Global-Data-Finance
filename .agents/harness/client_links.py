"""Maintain client-facing symlinks derived from a harness projection.

The projection remains the sole source of selected skills. Claude Code needs a
project-local discovery path, while its project instructions use ``CLAUDE.md``.
These two links expose existing project content and never copy or replace it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ClientLinkError(Exception):
    """A generated client link is stale or conflicts with project content."""


@dataclass(frozen=True)
class LinkSpec:
    source: Path
    target: Path
    link_target: Path
    source_is_directory: bool


def _specs(root: Path) -> tuple[LinkSpec, ...]:
    return (
        LinkSpec(
            source=root / '.agents' / 'skills',
            target=root / '.claude' / 'skills',
            link_target=Path('..') / '.agents' / 'skills',
            source_is_directory=True,
        ),
        LinkSpec(
            source=root / 'AGENTS.md',
            target=root / 'CLAUDE.md',
            link_target=Path('AGENTS.md'),
            source_is_directory=False,
        ),
    )


def _display(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _source_exists(spec: LinkSpec) -> bool:
    if spec.source_is_directory:
        return spec.source.is_dir()
    return spec.source.is_file()


def _is_managed_link(spec: LinkSpec) -> bool:
    return (
        spec.target.is_symlink() and spec.target.readlink() == spec.link_target
    )


def _exists(spec: LinkSpec) -> bool:
    return spec.target.exists() or spec.target.is_symlink()


def _conflict(spec: LinkSpec, root: Path) -> str:
    target = _display(spec.target, root)
    if spec.target.is_symlink():
        return (
            f'{target} points to {str(spec.target.readlink())!r}; '
            f'harness-sync manages only a link to {str(spec.link_target)!r}'
        )
    return f'{target} is project-owned; harness-sync will not replace it'


def _plan(root: Path) -> tuple[list[LinkSpec], list[LinkSpec]]:
    create: list[LinkSpec] = []
    remove: list[LinkSpec] = []
    conflicts: list[str] = []
    for spec in _specs(root):
        managed = _is_managed_link(spec)
        if _source_exists(spec):
            if managed:
                continue
            if _exists(spec):
                conflicts.append(_conflict(spec, root))
            else:
                create.append(spec)
        elif managed:
            remove.append(spec)
    if conflicts:
        raise ClientLinkError('; '.join(conflicts))
    return create, remove


def check(root: Path) -> None:
    """Raise when a managed client link differs without writing anything."""
    create, remove = _plan(root)
    stale = [_display(spec.target, root) for spec in (*create, *remove)]
    if stale:
        raise ClientLinkError(
            'generated client links are stale: ' + ', '.join(stale)
        )


def synchronize(root: Path) -> None:
    """Create or remove only the two exact generated relative symlinks."""
    create, remove = _plan(root)
    try:
        for spec in remove:
            spec.target.unlink()
        for spec in create:
            spec.target.parent.mkdir(parents=True, exist_ok=True)
            spec.target.symlink_to(
                spec.link_target,
                target_is_directory=spec.source_is_directory,
            )
    except OSError as exc:
        raise ClientLinkError(
            f'could not synchronize client links: {exc}'
        ) from exc
