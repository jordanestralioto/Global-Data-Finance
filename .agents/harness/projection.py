"""Staging, planning and atomic publication of the projection.

This module owns everything about the destination: the target layout under
``.agents``, the base directories every projection carries, planning against
the previous lock, the Git guard that keeps a replacement recoverable, the
staged move that never leaves a partial tree, and the deletion of deselected
managed paths. It is the only writer of ``.agents/harness.lock.json``, which
it writes last.

It never invokes a mirror generator and never decides what is selected; the
only subprocess it runs is the Git guard. Everything it removes or
overwrites is either listed as managed by the previous lock or is the target
path of a component being materialized by this run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness import selection
from harness.paths import HARNESS_ROOT
from harness.projection_modes import AGENTS_DIR_NAME, BASE_DIRS


class ProjectionError(Exception):
    """The projection cannot be published; the previous one stays in place."""


RESERVED_VALIDATION_PATH = '.agents/validation'


@dataclass(frozen=True)
class Replacement:
    component: str
    path: str


@dataclass(frozen=True)
class Plan:
    repo_root: Path
    managed_paths: tuple[str, ...]
    replacements: tuple[Replacement, ...]
    previous_managed: tuple[str, ...]
    removed_paths: tuple[str, ...]


def _agents_root(repo_root: Path) -> Path:
    return repo_root / AGENTS_DIR_NAME


def _relative(target: Path, repo_root: Path) -> str:
    return target.relative_to(repo_root).as_posix()


def _previous_managed_paths(
    repo_root: Path,
    catalog: dict[str, selection.CatalogEntry],
) -> tuple[str, ...]:
    lock_path = _agents_root(repo_root) / selection.LOCK_NAME
    if not lock_path.is_file():
        return ()
    try:
        payload = selection.read_lock(lock_path, catalog)
    except selection.SelectionError as exc:
        overlap = _overlapping_reserved_entries(lock_path)
        if overlap:
            raise ProjectionError(
                'reserved consumer-owned validation path in previous lock: '
                + ', '.join(overlap)
            ) from exc
        raise
    managed = payload.get('managedPaths')
    if not isinstance(managed, list) or not all(
        isinstance(item, str) for item in managed
    ):
        raise ProjectionError(
            f'{lock_path}: managedPaths must be a list of strings'
        )
    return tuple(managed)


def _overlaps_reserved_validation(path: str) -> bool:
    """Return whether a normalized path overlaps the reserved subtree."""
    return (
        path == RESERVED_VALIDATION_PATH
        or path.startswith(f'{RESERVED_VALIDATION_PATH}/')
        or RESERVED_VALIDATION_PATH.startswith(f'{path}/')
    )


def _overlapping_reserved_entries(lock_path: Path) -> tuple[str, ...]:
    """Inspect an invalid lock only to report reserved-path overlap."""
    try:
        payload: Any = json.loads(lock_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ()
    entries = (
        payload.get('managedPaths') if isinstance(payload, dict) else None
    )
    if not isinstance(entries, list):
        return ()
    return tuple(
        sorted(
            entry
            for entry in entries
            if isinstance(entry, str) and _overlaps_reserved_validation(entry)
        )
    )


def _git_guard(relative_path: str, repo_root: Path) -> None:
    completed = subprocess.run(
        [
            'git',
            'status',
            '--porcelain',
            '--untracked-files=all',
            '--ignored=matching',
            '--',
            relative_path,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout.strip():
        raise ProjectionError(
            f'{relative_path} has uncommitted or unrecoverable content; '
            'commit, stash or remove it before importing'
        )
    if completed.returncode != 0:
        raise ProjectionError(
            f'replacing {relative_path} requires the consumer to be a Git '
            'repository, because replaced project-owned content must stay '
            'recoverable'
        )


def _targets(resolution: selection.Resolution) -> tuple[str, ...]:
    component_targets = {
        component.target_relative for component in resolution.components
    }
    base_targets = {f'{AGENTS_DIR_NAME}/{name}' for name in BASE_DIRS}
    return tuple(sorted(component_targets | base_targets))


def plan(
    resolution: selection.Resolution,
    repo_root: Path,
    *,
    run_guard: bool = True,
    catalog: dict[str, selection.CatalogEntry] | None = None,
) -> Plan:
    if catalog is None:
        catalog = selection.load_catalog()
    previous = set(_previous_managed_paths(repo_root, catalog))
    targets = _targets(resolution)

    overlaps = sorted(
        path
        for path in previous | set(targets)
        if _overlaps_reserved_validation(path)
    )
    if overlaps:
        raise ProjectionError(
            'reserved consumer-owned validation path cannot be managed: '
            + ', '.join(overlaps)
        )

    replacements: list[Replacement] = []
    for target in targets:
        if target in previous:
            continue
        disk_path = repo_root / target
        if not disk_path.exists():
            continue
        if run_guard:
            _git_guard(target, repo_root)
        component = _component_for_target(resolution, target)
        replacements.append(Replacement(component=component, path=target))

    removed = tuple(sorted(previous - set(targets)))
    return Plan(
        repo_root=repo_root,
        managed_paths=targets,
        replacements=tuple(replacements),
        previous_managed=tuple(sorted(previous)),
        removed_paths=removed,
    )


def _component_for_target(
    resolution: selection.Resolution, target: str
) -> str:
    for component in resolution.components:
        if component.target_relative == target:
            return component.id
    return target


def _ignored_entry(path: Path) -> bool:
    return (path.is_dir() and path.name == '__pycache__') or (
        path.is_file() and path.suffix == '.pyc'
    )


def _copy_entry(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, destination)
        return
    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        if _ignored_entry(child):
            continue
        _copy_entry(child, destination / child.name)


def projection_content_matches(
    resolution: selection.Resolution,
    repo_root: Path,
) -> bool:
    if not all(
        (repo_root / AGENTS_DIR_NAME / name).exists() for name in BASE_DIRS
    ):
        return False
    return all(
        (disk_path := repo_root / component.target_relative).exists()
        and selection.component_hash(disk_path) == component.hash
        for component in resolution.components
    )


def _staged_tree(resolution: selection.Resolution, staging: Path) -> None:
    staged_root = staging / AGENTS_DIR_NAME
    for component in resolution.components:
        destination = staged_root / Path(component.source_ref)
        _copy_entry(component.source, destination)
    for name in BASE_DIRS:
        source = HARNESS_ROOT / name
        if not source.exists():
            raise ProjectionError(f'base directory {name} is missing')
        _copy_entry(source, staged_root / name)


def _rollback_root(staging: Path) -> Path:
    return staging / 'rollback'


def _move_to_rollback(
    relative_path: str, repo_root: Path, rollback: Path
) -> None:
    disk_path = repo_root / relative_path
    if not disk_path.exists() and not disk_path.is_symlink():
        return
    destination = rollback / Path(relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(disk_path), str(destination))


def _restore_rollback(
    repo_root: Path, rollback: Path, displaced: list[str]
) -> None:
    for relative_path in reversed(displaced):
        source = rollback / Path(relative_path)
        if source.exists() or source.is_symlink():
            destination = repo_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))


def _prune_empty_parents(
    repo_root: Path, agents_root: Path, removed_paths: tuple[str, ...]
) -> None:
    for relative_path in removed_paths:
        parent = (repo_root / relative_path).parent
        while (
            parent != agents_root
            and parent.is_dir()
            and not any(parent.iterdir())
        ):
            parent.rmdir()
            parent = parent.parent


def publish(
    resolution: selection.Resolution,
    plan: Plan,
    lock_bytes: bytes,
) -> None:
    repo_root = plan.repo_root
    agents_root = _agents_root(repo_root)
    agents_root.mkdir(parents=True, exist_ok=True)
    staging = agents_root / selection.STAGING_DIR_NAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    rollback = _rollback_root(staging)
    rollback.mkdir(parents=True, exist_ok=True)

    displaced: list[str] = []
    placed: list[str] = []
    try:
        _staged_tree(resolution, staging)

        to_displace = sorted(set(plan.removed_paths) | set(plan.managed_paths))
        for relative_path in to_displace:
            disk_path = repo_root / relative_path
            if disk_path.exists() or disk_path.is_symlink():
                _move_to_rollback(relative_path, repo_root, rollback)
                displaced.append(relative_path)

        _prune_empty_parents(repo_root, agents_root, plan.removed_paths)

        for relative_path in plan.managed_paths:
            staged_entry = staging / Path(relative_path)
            destination = repo_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_entry), str(destination))
            placed.append(relative_path)

        lock_path = agents_root / selection.LOCK_NAME
        lock_tmp = staging / f'{selection.LOCK_NAME}.tmp'
        with open(lock_tmp, 'wb') as handle:
            handle.write(lock_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(lock_tmp, lock_path)
    except Exception as exc:
        for relative_path in reversed(placed):
            disk_path = repo_root / relative_path
            if disk_path.is_dir():
                shutil.rmtree(disk_path, ignore_errors=True)
            elif disk_path.exists() or disk_path.is_symlink():
                disk_path.unlink()
        _restore_rollback(repo_root, rollback, displaced)
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectionError(f'publish failed: {exc}') from exc
    shutil.rmtree(staging, ignore_errors=True)
