#!/usr/bin/env python3
"""Read-only uv lockfile checks used by the synchronization gate."""

from __future__ import annotations

from pathlib import Path

from scripts.process_runner import ProcessRunnerError, run_process

UV_LOCK_CHECK = ('uv', 'lock', '--check')


class LockfileInfrastructureError(RuntimeError):
    """Raised when a native lockfile check cannot be started or run."""


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


def is_lockfile_in_sync(
    manifest_path: Path,
    manifest_dir: Path,
    existing_locks: list[str],
    root: Path,
) -> bool:
    """Return whether a native package manager confirms lockfile coherence.

    No universal wall-clock budget is imposed here. A native command that
    returns non-zero means the existing lockfile is not confirmed as coherent.
    A missing tool or child-process execution error is infrastructure failure
    and must remain distinguishable from that deterministic mismatch.
    """
    target_dir = root / manifest_dir
    if manifest_path.name != 'pyproject.toml' or existing_locks != ['uv.lock']:
        return False

    command_text = ' '.join(UV_LOCK_CHECK)
    try:
        result = run_process(
            list(UV_LOCK_CHECK),
            cwd=target_dir,
            check=False,
        )
    except ProcessRunnerError as err:
        raise LockfileInfrastructureError(
            f'Unable to execute native lockfile check "{command_text}" '
            f'for {manifest_path.as_posix()} (uv.lock): {err}'
        ) from err
    return result.returncode == 0
