#!/usr/bin/env python3
"""Inspect staged Git changes without flattening rename/copy relationships."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.git_changes import is_external_harness_path
from scripts.process_runner import ProcessRunnerError, run_process
from scripts.workspace_members import GitInspectionError, normalize_path


@dataclass(frozen=True)
class StagedChange:
    """One staged change, retaining both sides of renames and copies."""

    status: str
    old_path: str | None
    new_path: str


def _git_error(err: BaseException) -> GitInspectionError:
    detail = getattr(err, 'stderr', None) or str(err)
    return GitInspectionError(str(detail).strip())


def _parse_name_status(output: str) -> list[StagedChange]:
    fields = output.split('\0')
    changes: list[StagedChange] = []
    index = 0
    while index < len(fields) - 1:
        status = fields[index]
        index += 1
        if not status:
            continue
        kind = status[0]
        if kind in {'R', 'C'}:
            if index + 1 >= len(fields):
                raise GitInspectionError(
                    'malformed Git name-status output for rename/copy'
                )
            changes.append(
                StagedChange(
                    kind,
                    normalize_path(fields[index]),
                    normalize_path(fields[index + 1]),
                )
            )
            index += 2
            continue
        if index >= len(fields):
            raise GitInspectionError('malformed Git name-status output')
        changes.append(StagedChange(kind, None, normalize_path(fields[index])))
        index += 1
    return changes


def get_staged_changes(repo_root: Path | None = None) -> list[StagedChange]:
    """Return staged changes with rename and copy relationships intact."""
    try:
        result = run_process(
            ['git', 'diff', '--cached', '--name-status', '-z', '-M', '-C'],
            cwd=repo_root or Path.cwd(),
        )
    except ProcessRunnerError as err:
        raise _git_error(err) from err
    return [
        change
        for change in _parse_name_status(result.stdout)
        if not is_external_harness_path(change.new_path)
    ]


def status_for_path(
    path: str,
    staged_statuses: dict[str, str] | None,
    staged_changes: list[StagedChange] | None,
) -> str | None:
    """Return the status for an effective staged path."""
    normalized = normalize_path(path)
    if staged_changes is not None:
        for change in staged_changes:
            if change.new_path == normalized:
                return change.status
        return None
    if staged_statuses is not None:
        return staged_statuses.get(normalized)
    return None
