#!/usr/bin/env python3
"""Read staged Git changes and revision ranges for local quality gates."""

from __future__ import annotations

from pathlib import Path

from scripts.process_runner import (
    ProcessResult,
    ProcessRunnerError,
    run_process,
)

# The tracked projection that harness-sync publishes. Hooks execute scripts
# from it, so the operational scan and shell syntax gate inspect it.
TRACKED_PROJECTION_ROOTS = ('.agents/',)
CLIENT_MIRROR_ROOTS = (
    '.claude/',
    '.codex/',
    '.opencode/',
    '.github/prompts/',
)
EXTERNAL_HARNESS_ROOTS = (*TRACKED_PROJECTION_ROOTS, *CLIENT_MIRROR_ROOTS)


def _excluded_roots(include_projection: bool) -> tuple[str, ...]:
    """Return the generated roots a Git inspection must leave out."""
    return (
        CLIENT_MIRROR_ROOTS if include_projection else EXTERNAL_HARNESS_ROOTS
    )


def _is_under(path: str, roots: tuple[str, ...]) -> bool:
    """Return whether a repository path lies under one of the roots."""
    normalized = path.replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    return any(
        normalized == root.rstrip('/') or normalized.startswith(root)
        for root in roots
    )


def is_external_harness_path(
    path: str, *, include_projection: bool = False
) -> bool:
    """Return whether a gate must skip a generated harness path."""
    return _is_under(path, _excluded_roots(include_projection))


def is_tracked_projection_path(path: str) -> bool:
    """Return whether a path belongs to the tracked .agents projection."""
    return _is_under(path, TRACKED_PROJECTION_ROOTS)


def _pathspecs(
    target_files: list[str] | None, *, include_projection: bool = False
) -> list[str]:
    """Build Git pathspecs that exclude generated harness roots."""
    if target_files:
        included = [
            path
            for path in target_files
            if not is_external_harness_path(
                path, include_projection=include_projection
            )
        ]
        if not included:
            return []
    else:
        included = ['.']

    excluded = [
        f':(exclude){root}**' for root in _excluded_roots(include_projection)
    ]
    return [*included, *excluded]


class GitInspectionError(RuntimeError):
    """Raised when a required Git inspection cannot be completed."""


def run_git_command(
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


def _split_range(revision_range: str) -> tuple[str, str, str]:
    """Split a Git A..B or A...B range into base, separator, and target."""
    separator = '...' if '...' in revision_range else '..'
    if separator not in revision_range:
        raise GitInspectionError(
            'revision range must use the Git A..B or A...B notation'
        )
    base, _, target = revision_range.rpartition(separator)
    if not target:
        raise GitInspectionError(
            'revision range must include an ending revision'
        )
    return base or 'HEAD', separator, target


def resolve_commit(revision: str, repo_root: Path | None = None) -> str:
    """Return the full commit name denoted by one revision expression."""
    result = run_git_command(
        ['rev-parse', '--verify', f'{revision}^{{commit}}'], _root(repo_root)
    )
    return result.stdout.strip()


def range_target_revision(
    revision_range: str, repo_root: Path | None = None
) -> str:
    """Validate a Git range and return its right-side revision."""
    _, _, target = _split_range(revision_range)
    return resolve_commit(target, repo_root)


def range_base_revision(
    revision_range: str, repo_root: Path | None = None
) -> str:
    """Return the commit that a Git range diff compares its target against."""
    base, separator, target = _split_range(revision_range)
    base_commit = resolve_commit(base, repo_root)
    if separator == '..':
        return base_commit
    result = run_git_command(
        ['merge-base', base_commit, resolve_commit(target, repo_root)],
        _root(repo_root),
    )
    return result.stdout.strip()


def find_base_tag(repo_root: Path | None = None) -> str | None:
    """Find the most recent ancestor tag, or None if untagged."""
    root = _root(repo_root)
    result = run_git_command(
        ['describe', '--tags', '--abbrev=0'], root, check=False
    )
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
    return run_git_command(command, root, check=False).stdout


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
    result = run_git_command(command, root, check=False)
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
    include_projection: bool = False,
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
    pathspecs = _pathspecs(target_files, include_projection=include_projection)
    if target_files and not pathspecs:
        return ''
    command.extend(['--', *pathspecs])
    return run_git_command(command, root).stdout


def get_changed_paths(
    *,
    revision_range: str | None = None,
    diff_filter: str = 'ACMR',
    repo_root: Path | None = None,
    include_projection: bool = False,
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
    command.extend(
        ['--', *_pathspecs(None, include_projection=include_projection)]
    )
    return sorted(
        path
        for path in run_git_command(command, root).stdout.splitlines()
        if path
        and not is_external_harness_path(
            path, include_projection=include_projection
        )
    )


def _show_object(
    object_name: str, root: Path, encoding_errors: str
) -> str | None:
    """Return one Git blob as text, or None when it does not exist."""
    exists = run_git_command(
        ['cat-file', '-e', object_name], root, check=False
    )
    if exists.returncode != 0:
        return None
    return run_git_command(
        ['show', object_name], root, encoding_errors=encoding_errors
    ).stdout


def read_git_file(
    file_path: str,
    *,
    revision_range: str | None = None,
    repo_root: Path | None = None,
    encoding_errors: str = 'strict',
    include_projection: bool = False,
) -> str | None:
    """Read a Git snapshot file with the requested UTF-8 error handler."""
    if is_external_harness_path(
        file_path, include_projection=include_projection
    ):
        return None
    root = _root(repo_root)
    if revision_range is not None:
        target = range_target_revision(revision_range, root)
        return _show_object(f'{target}:{file_path}', root, encoding_errors)
    index_entry = run_git_command(
        ['ls-files', '--stage', '--', file_path], root
    )
    if not index_entry.stdout.strip():
        return None
    return run_git_command(
        ['show', f':{file_path}'], root, encoding_errors=encoding_errors
    ).stdout


def read_git_base_file(
    file_path: str,
    *,
    revision_range: str | None = None,
    repo_root: Path | None = None,
    encoding_errors: str = 'strict',
) -> str | None:
    """Read the version that a staged or ranged diff compares a file with."""
    if is_external_harness_path(file_path):
        return None
    root = _root(repo_root)
    if revision_range is not None:
        base = range_base_revision(revision_range, root)
    else:
        head = run_git_command(
            ['rev-parse', '--verify', '--quiet', 'HEAD^{commit}'],
            root,
            check=False,
        )
        if head.returncode != 0:
            return None
        base = head.stdout.strip()
    return _show_object(f'{base}:{file_path}', root, encoding_errors)
