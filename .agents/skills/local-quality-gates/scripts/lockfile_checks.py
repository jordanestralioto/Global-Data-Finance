#!/usr/bin/env python3
"""Native package-manager checks used by the lockfile synchronization gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from workspace_members import normalize_path, read_staged_git_file

DEPENDENCY_KEYS = (
    'dependencies',
    'devDependencies',
    'peerDependencies',
    'optionalDependencies',
    'bundleDependencies',
    'bundledDependencies',
)
NATIVE_LOCKFILE_COMMANDS: dict[tuple[str, str], tuple[str, ...]] = {
    ('pyproject.toml', 'uv.lock'): ('uv', 'lock', '--check'),
    ('pyproject.toml', 'poetry.lock'): ('poetry', 'check', '--lock'),
    ('Cargo.toml', 'Cargo.lock'): ('cargo', 'check', '--locked'),
}


class LockfileInfrastructureError(RuntimeError):
    """Raised when a native lockfile check cannot be started or run."""


class UnstagedDependencyChangesError(RuntimeError):
    """Raised when a native check would inspect a different Git snapshot."""


def _ensure_staged_snapshot(
    manifest_path: Path,
    lock_path: Path,
    root: Path,
) -> None:
    paths = (manifest_path.as_posix(), lock_path.as_posix())
    try:
        result = subprocess.run(
            ['git', 'diff', '--quiet', '--', *paths],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as err:
        raise LockfileInfrastructureError(
            f'Unable to compare the Git index with the working tree: {err}'
        ) from err
    if result.returncode == 1:
        raise UnstagedDependencyChangesError(
            f'{manifest_path.as_posix()}: Unstaged changes in the manifest '
            f'or {lock_path.as_posix()} prevent a native lockfile check '
            'against the staged snapshot. Stage the intended files or '
            'restore the unstaged edits before committing.'
        )
    if result.returncode != 0:
        raise LockfileInfrastructureError(
            'Unable to compare the Git index with the working tree for '
            f'{manifest_path.as_posix()} and {lock_path.as_posix()}: '
            f'{result.stderr.strip() or result.returncode}'
        )


def missing_lockfile_error(
    manifest_path: Path,
    scope: str,
    lock_names: tuple[str, ...],
    staged_index: bool,
) -> str:
    """Format the error for a manifest with no supported lockfile."""
    names = ', '.join(lock_names)
    location = 'Git index' if staged_index else 'working tree'
    return (
        f'{manifest_path.as_posix()}: Manifest modified without a supported '
        f'{scope} lockfile in the {location} ({names}).'
    )


def has_declared_dependencies(
    manifest_path: Path,
    root: Path,
    read_index: bool = False,
) -> bool:
    """Return whether a staged manifest declares dependency data."""
    if manifest_path.name != 'package.json':
        return True

    content = None
    if read_index:
        content = read_staged_git_file(
            normalize_path(str(manifest_path)), root
        )
    if content is None:
        file_on_disk = root / manifest_path
        if not file_on_disk.exists():
            return True
        try:
            content = file_on_disk.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return True

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    return any(bool(data.get(key)) for key in DEPENDENCY_KEYS)


def is_lockfile_in_sync(
    manifest_path: Path,
    manifest_dir: Path,
    existing_locks: list[str],
    root: Path,
    check_staged_snapshot: bool = False,
) -> bool:
    """Return whether a native package manager confirms lockfile coherence.

    No universal wall-clock budget is imposed here. A native command that
    returns non-zero means the existing lockfile is not confirmed as coherent.
    A missing tool or subprocess execution error is infrastructure failure and
    must remain distinguishable from that deterministic mismatch.
    """
    target_dir = root / manifest_dir
    for lock_name in existing_locks:
        command = NATIVE_LOCKFILE_COMMANDS.get((manifest_path.name, lock_name))
        if command is None:
            continue
        if check_staged_snapshot:
            _ensure_staged_snapshot(
                manifest_path, manifest_dir / lock_name, root
            )
        command_text = ' '.join(command)
        try:
            result = subprocess.run(
                list(command),
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as err:
            raise LockfileInfrastructureError(
                f'Unable to execute native lockfile check "{command_text}" '
                f'for {manifest_path.as_posix()} ({lock_name}): {err}'
            ) from err
        if result.returncode == 0:
            return True
    return False
