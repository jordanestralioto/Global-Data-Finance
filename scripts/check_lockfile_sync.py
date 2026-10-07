#!/usr/bin/env python3
"""Check lockfile synchronization for Git staged manifest changes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import lockfile_checks
from scripts.staged_changes import (
    StagedChange,
    get_staged_changes,
    status_for_path,
)
from scripts.workspace_members import (
    GitInspectionError,
    index_file_exists,
    is_manifest_member_of_workspace,
    normalize_path,
)

MANIFEST_LOCKFILE_PAIRS: dict[str, tuple[str, ...]] = {
    'pyproject.toml': ('uv.lock',),
}
LOCKFILE_UPDATED_STATUSES = frozenset({'A', 'M', 'R', 'C'})


def _lockfile_path(manifest_dir: Path, lock_name: str) -> str:
    return normalize_path(str(manifest_dir / lock_name))


def _existing_lockfiles(
    manifest_dir: Path,
    candidate_locks: tuple[str, ...],
    root: Path,
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> list[str]:
    if staged_statuses is None and staged_changes is None:
        return [
            lock_name
            for lock_name in candidate_locks
            if (root / manifest_dir / lock_name).exists()
        ]
    return [
        lock_name
        for lock_name in candidate_locks
        if index_file_exists(_lockfile_path(manifest_dir, lock_name), root)
    ]


def _deleted_lockfiles(
    manifest_dir: Path,
    candidate_locks: tuple[str, ...],
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> list[str]:
    if staged_statuses is None and staged_changes is None:
        return []
    return [
        lock_name
        for lock_name in candidate_locks
        if _staged_status_for_path(
            _lockfile_path(manifest_dir, lock_name),
            staged_statuses,
            staged_changes,
        )
        == 'D'
    ]


def _staged_status_for_path(
    path: str,
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None,
) -> str | None:
    return status_for_path(path, staged_statuses, staged_changes)


def _lockfile_was_updated(
    manifest_dir: Path,
    lock_name: str,
    staged_set: set[str],
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> bool:
    path = _lockfile_path(manifest_dir, lock_name)
    if staged_statuses is None and staged_changes is None:
        return path in staged_set
    return (
        _staged_status_for_path(path, staged_statuses, staged_changes)
        in LOCKFILE_UPDATED_STATUSES
    )


def _has_updated_lockfile(
    manifest_dir: Path,
    lock_names: list[str],
    staged_set: set[str],
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> bool:
    return any(
        _lockfile_was_updated(
            manifest_dir,
            lock_name,
            staged_set,
            staged_statuses,
            staged_changes,
        )
        for lock_name in lock_names
    )


def _deletion_error(
    manifest_path: Path,
    scope: str,
    lock_names: list[str],
) -> str:
    names = ', '.join(lock_names)
    return (
        f'{manifest_path.as_posix()}: Manifest modified while deleting '
        f'{scope} lockfile ({names}); a deleted lockfile does not satisfy '
        'dependency synchronization.'
    )


def _missing_update_error(
    manifest_path: Path,
    scope: str,
    lock_names: list[str],
) -> str:
    names = ', '.join(lock_names)
    label = (
        'local lockfile' if scope in {'local', 'root'} else f'{scope} lockfile'
    )
    return (
        f'{manifest_path.as_posix()}: Manifest modified without updating '
        f'{label} ({names}).'
    )


def _check_lockfiles_for_manifest(
    manifest_path: Path,
    manifest_dir: Path,
    candidate_locks: tuple[str, ...],
    scope: str,
    root: Path,
    staged_set: set[str],
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> list[str] | None:
    existing = _existing_lockfiles(
        manifest_dir,
        candidate_locks,
        root,
        staged_statuses,
        staged_changes,
    )
    deleted = _deleted_lockfiles(
        manifest_dir,
        candidate_locks,
        staged_statuses,
        staged_changes,
    )
    if existing:
        if _has_updated_lockfile(
            manifest_dir,
            existing,
            staged_set,
            staged_statuses,
            staged_changes,
        ):
            return []
        if deleted:
            return [_deletion_error(manifest_path, scope, deleted)]
        if lockfile_checks.is_lockfile_in_sync(
            manifest_path, manifest_dir, existing, root
        ):
            return []
        return [_missing_update_error(manifest_path, scope, existing)]
    if deleted:
        return [_deletion_error(manifest_path, scope, deleted)]
    return None


def _check_single_manifest_sync(
    manifest_path: Path,
    candidate_locks: tuple[str, ...],
    staged_set: set[str],
    root: Path,
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None = None,
) -> list[str]:
    manifest_dir = manifest_path.parent
    manifest_name = manifest_path.name

    local_result = _check_lockfiles_for_manifest(
        manifest_path,
        manifest_dir,
        candidate_locks,
        'local' if manifest_dir != Path() else 'root',
        root,
        staged_set,
        staged_statuses,
        staged_changes,
    )
    if local_result is not None:
        return local_result

    if manifest_dir != Path():
        is_member = is_manifest_member_of_workspace(
            manifest_path, manifest_name, root
        )
        root_result = _check_lockfiles_for_manifest(
            manifest_path,
            Path(),
            candidate_locks,
            'shared root',
            root,
            staged_set,
            staged_statuses,
            staged_changes,
        )
        if is_member:
            if root_result is not None:
                return root_result
            return [
                lockfile_checks.missing_lockfile_error(
                    manifest_path,
                    'shared root',
                    candidate_locks,
                    staged_statuses is not None or staged_changes is not None,
                )
            ]
        return [
            f'{manifest_path.as_posix()}: Manifest modified in subdirectory '
            f'without local lockfile and does not belong to a proven '
            f'workspace in {manifest_name}.'
        ]

    return [
        lockfile_checks.missing_lockfile_error(
            manifest_path,
            'root',
            candidate_locks,
            staged_statuses is not None or staged_changes is not None,
        )
    ]


def check_manifest_lockfile_sync(
    staged_files: list[str],
    repo_root: Path | None = None,
    staged_statuses: dict[str, str] | None = None,
    staged_changes: list[StagedChange] | None = None,
) -> list[str]:
    """Verify staged manifests; true deletions still require lock sync.

    Rename and copy sources are represented only as ``old_path`` on their
    change record, so they are not mistaken for deleted manifests.
    """
    root = repo_root or Path.cwd()
    if staged_changes is not None:
        staged_set = {change.new_path for change in staged_changes}
    elif staged_statuses is not None:
        staged_set = set(staged_statuses)
    else:
        staged_set = {normalize_path(path) for path in staged_files}
    errors: list[str] = []
    for staged_file in staged_files:
        manifest_path = Path(staged_file)
        candidate_locks = MANIFEST_LOCKFILE_PAIRS.get(manifest_path.name)
        if candidate_locks is None:
            continue
        errors.extend(
            _check_single_manifest_sync(
                manifest_path,
                candidate_locks,
                staged_set,
                root,
                staged_statuses,
                staged_changes,
            )
        )
    return errors


def main() -> int:
    """Check that staged dependency metadata agrees with the lockfile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--files',
        nargs='*',
        help='List of staged files. If omitted, queries Git directly.',
    )
    args = parser.parse_args()

    try:
        if args.files is None:
            staged_changes = get_staged_changes()
            staged_files = [change.new_path for change in staged_changes]
            staged_statuses = None
        else:
            staged_files = args.files
            staged_statuses = None
            staged_changes = None
        manifest_staged = any(
            Path(path).name in MANIFEST_LOCKFILE_PAIRS for path in staged_files
        )
        if not staged_files or not manifest_staged:
            sys.stdout.write(
                'SKIP [DEPENDENCY_SYNC]: No staged manifest files to '
                'inspect.\n'
            )
            return 0
        errors = check_manifest_lockfile_sync(
            staged_files,
            staged_statuses=staged_statuses,
            staged_changes=staged_changes,
        )
    except lockfile_checks.LockfileInfrastructureError as err:
        sys.stderr.write(
            'ERROR [DEPENDENCY_SYNC]: unable to execute native lockfile '
            f'check: {err}\n'
        )
        return 2
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [DEPENDENCY_SYNC]: unable to inspect staged Git changes: '
            f'{err}\n'
        )
        return 2

    if errors:
        sys.stderr.write(
            'FAIL [DEPENDENCY_SYNC]: Manifest staged without corresponding '
            'lockfile:\n'
        )
        for error_msg in errors:
            sys.stderr.write(f'  • {error_msg}\n')
        sys.stderr.write(
            '\nResolution: Update the lockfile deliberately outside this hook '
            'with `uv lock`, then stage it before committing.\n'
        )
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
