#!/usr/bin/env python3
"""Read staged Git changes and revision ranges for local quality gates."""

from __future__ import annotations

from pathlib import Path

from scripts.process_runner import (
    ProcessResult,
    ProcessRunnerError,
    run_process,
)

EXTERNAL_HARNESS_ROOTS = (
    '.agents/',
    '.claude/',
    '.codex/',
    '.opencode/',
    '.github/prompts/',
)


def is_external_harness_path(path: str) -> bool:
    """Return whether a repository path belongs to a generated projection."""
    normalized = path.replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    return any(
        normalized == root.rstrip('/') or normalized.startswith(root)
        for root in EXTERNAL_HARNESS_ROOTS
    )


def _pathspecs(target_files: list[str] | None) -> list[str]:
    """Build Git pathspecs that exclude generated harness projections."""
    if target_files:
        included = [
            path for path in target_files if not is_external_harness_path(path)
        ]
        if not included:
            return []
    else:
        included = ['.']

    excluded = [f':(exclude){root}**' for root in EXTERNAL_HARNESS_ROOTS]
    return [*included, *excluded]


class GitInspectionError(RuntimeError):
    """Raised when a required Git inspection cannot be completed."""


def _run_git(
    arguments: list[str],
    root: Path,
    *,
    check: bool = True,
    encoding_errors: str = 'strict',
) -> ProcessResult:
    """Run Git in a repository and translate infrastructure failures."""
    try:
        return run_process(
            ['git', *arguments],
            cwd=root,
            check=check,
            encoding_errors=encoding_errors,
        )
    except ProcessRunnerError as err:
        raise GitInspectionError(str(err)) from err


def _root(repo_root: Path | None) -> Path:
    """Return the supplied repository root or the current working directory."""
    return repo_root or Path.cwd()


def range_target_revision(
    revision_range: str, repo_root: Path | None = None
) -> str:
    """Validate a Git range and return its right-side revision."""
    separator = '...' if '...' in revision_range else '..'
    if separator not in revision_range:
        raise GitInspectionError(
            'revision range must use the Git A..B or A...B notation'
        )
    _, _, target = revision_range.rpartition(separator)
    if not target:
        raise GitInspectionError(
            'revision range must include an ending revision'
        )

    result = _run_git(
        ['rev-parse', '--verify', f'{target}^{{commit}}'], _root(repo_root)
    )
    return result.stdout.strip()


def find_base_tag(repo_root: Path | None = None) -> str | None:
    """Find the most recent ancestor tag, or None if untagged."""
    root = _root(repo_root)
    result = _run_git(['describe', '--tags', '--abbrev=0'], root, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def get_base_staged_diff(
    *,
    context_lines: int,
    base_tag: str,
    target_files: list[str] | None = None,
    no_renames: bool = False,
    repo_root: Path | None = None,
) -> str:
    """Return unified diff from ancestor base_tag to the staged index."""
    root = _root(repo_root)
    command = [
        'diff',
        '--no-color',
        f'-U{context_lines}',
        '--cached',
        base_tag,
    ]
    if no_renames:
        command.append('--no-renames')
    pathspecs = _pathspecs(target_files)
    if target_files and not pathspecs:
        return ''
    command.extend(['--', *pathspecs])
    return _run_git(command, root, check=False).stdout


def get_base_staged_deleted_paths(
    base_tag: str,
    repo_root: Path | None = None,
) -> set[str]:
    """Return paths deleted between base_tag and the staged index."""
    root = _root(repo_root)
    command = [
        'diff',
        '--no-color',
        '--name-only',
        '--diff-filter=D',
        '--cached',
        base_tag,
    ]
    command.extend(['--', *_pathspecs(None)])
    result = _run_git(command, root, check=False)
    if result.returncode != 0:
        return set()
    return {
        path
        for path in result.stdout.splitlines()
        if path and not is_external_harness_path(path)
    }


def get_diff(
    *,
    context_lines: int,
    target_files: list[str] | None = None,
    revision_range: str | None = None,
    no_renames: bool = False,
    repo_root: Path | None = None,
) -> str:
    """Return a unified diff from the index or an explicit revision range."""
    root = _root(repo_root)
    command = ['diff', '--no-color', f'-U{context_lines}']
    if no_renames:
        command.append('--no-renames')
    if revision_range is None:
        command.append('--cached')
    else:
        range_target_revision(revision_range, root)
        command.append(revision_range)
    pathspecs = _pathspecs(target_files)
    if target_files and not pathspecs:
        return ''
    command.extend(['--', *pathspecs])
    return _run_git(command, root).stdout


def get_changed_paths(
    *,
    revision_range: str | None = None,
    diff_filter: str = 'ACMR',
    repo_root: Path | None = None,
) -> list[str]:
    """Return paths added, copied, modified, or renamed in a Git comparison."""
    root = _root(repo_root)
    command = [
        'diff',
        '--no-color',
        '--name-only',
        f'--diff-filter={diff_filter}',
    ]
    if revision_range is None:
        command.append('--cached')
    else:
        range_target_revision(revision_range, root)
        command.append(revision_range)
    command.extend(['--', *_pathspecs(None)])
    return sorted(
        path
        for path in _run_git(command, root).stdout.splitlines()
        if path and not is_external_harness_path(path)
    )


def read_git_file(
    file_path: str,
    *,
    revision_range: str | None = None,
    repo_root: Path | None = None,
    encoding_errors: str = 'strict',
) -> str | None:
    """Read a Git snapshot file with the requested UTF-8 error handler."""
    if is_external_harness_path(file_path):
        return None
    root = _root(repo_root)
    if revision_range is None:
        index_entry = _run_git(['ls-files', '--stage', '--', file_path], root)
        if not index_entry.stdout.strip():
            return None
        object_name = f':{file_path}'
    else:
        target = range_target_revision(revision_range, root)
        object_name = f'{target}:{file_path}'
        exists = _run_git(['cat-file', '-e', object_name], root, check=False)
        if exists.returncode != 0:
            return None

    return _run_git(
        ['show', object_name], root, encoding_errors=encoding_errors
    ).stdout
