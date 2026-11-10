"""Derive review coverage from an explicit Git scope."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from runtime_support import REPO_ROOT, ArtifactError, normalize_paths


def git_output(*args: str) -> bytes:
    # Compare executable modes even when the consumer disables Git mode tracking.
    result = subprocess.run(
        ['git', '-c', 'core.filemode=true', *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ArtifactError('Review scope could not be resolved with Git.')
    return result.stdout


def git_files(*args: str) -> set[str]:
    return {
        os.fsdecode(path) for path in git_output(*args).split(b'\0') if path
    }


def git_commit(ref: str) -> str:
    if not ref or ref.startswith('-'):
        raise ArtifactError('Review refs must name Git commits.')
    return os.fsdecode(
        git_output('rev-parse', '--verify', f'{ref}^{{commit}}')
    ).strip()


def scoped_files(session: dict[str, Any], session_dir: Path) -> set[str]:
    change = session['change']
    base, head = change.get('baseRef'), change.get('headRef')
    scope = session.get('scope', {})
    if not isinstance(scope, dict):
        raise ArtifactError('Review scope must be an object.')
    mode = scope.get('mode', 'refs' if base or head else 'worktree')
    paths = scope.get('paths', [])
    if not isinstance(paths, list) or any(
        not isinstance(path, str) or not path for path in paths
    ):
        raise ArtifactError('Review scope paths must be nonempty strings.')
    paths = normalize_paths(paths)
    if mode == 'refs':
        if (
            not base
            or not head
            or base.startswith('-')
            or head.startswith('-')
        ):
            raise ArtifactError(
                'Review diff requires valid baseRef and headRef.'
            )
        base_commit, head_commit = git_commit(base), git_commit(head)
        if (scope.get('baseCommit'), scope.get('headCommit')) != (
            base_commit,
            head_commit,
        ):
            raise ArtifactError(
                'Review refs changed or lack pinned commits; start a new session.'
            )
        files = git_files(
            'diff',
            '--name-only',
            '-z',
            '--no-ext-diff',
            '--no-renames',
            f'{base_commit}...{head_commit}',
            '--',
        )
    elif mode in {'worktree', 'staged'}:
        if base or head:
            raise ArtifactError('Git refs require the refs review scope.')
        files = git_files(
            'diff',
            '--name-only',
            '-z',
            '--no-ext-diff',
            '--no-renames',
            '--cached',
            '--',
        )
        if mode == 'worktree':
            files.update(
                git_files(
                    'diff',
                    '--name-only',
                    '-z',
                    '--no-ext-diff',
                    '--no-renames',
                    '--',
                )
            )
            files.update(
                git_files('ls-files', '--others', '--exclude-standard', '-z')
            )
    else:
        raise ArtifactError(f'Unknown review scope: {mode!r}')
    own_session = session_dir.relative_to(REPO_ROOT).as_posix()
    return {
        path
        for path in files
        if not Path(path).is_relative_to(own_session)
        and (
            not paths
            or any(Path(path).is_relative_to(prefix) for prefix in paths)
        )
    }


def checkout_gaps(
    session: dict[str, Any],
    session_dir: Path,
    evidence_path: str | None,
) -> list[str]:
    head = session['change'].get('headRef')
    if not head and session.get('scope', {}).get('mode') != 'staged':
        return []
    reasons = []
    if head and git_commit('HEAD') != session['scope']['headCommit']:
        reasons.append('Refs review requires the checkout at headRef.')
    dirty = git_files(
        'diff',
        '--name-only',
        '-z',
        '--no-ext-diff',
        *(['HEAD'] if head else []),
        '--',
    )
    dirty.update(git_files('ls-files', '--others', '--exclude-standard', '-z'))
    own_session = session_dir.relative_to(REPO_ROOT).as_posix()
    dirty = {
        path
        for path in dirty
        if not Path(path).is_relative_to(own_session) and path != evidence_path
    }
    if dirty:
        reasons.append(
            (
                'Refs review requires a clean checkout: '
                if head
                else 'Staged review requires the working tree to match the index: '
            )
            + ', '.join(sorted(dirty))
        )
    return reasons


def scope_gaps(
    session: dict[str, Any], session_dir: Path, evidence_path: str | None
) -> list[str]:
    try:
        actual = scoped_files(session, session_dir)
        reasons = checkout_gaps(session, session_dir, evidence_path)
    except (ArtifactError, OSError, TypeError, ValueError) as exc:
        return [str(exc)]
    declared = set(session['changedFiles'])
    if evidence_path:
        actual.discard(evidence_path)
        declared.discard(evidence_path)
    if not actual:
        reasons.append('No Git changes exist in the review scope.')
    missing = sorted(actual - declared)
    if missing:
        reasons.append('Files missing from review diff: ' + ', '.join(missing))
    if session['change'].get('baseRef') or session['change'].get('headRef'):
        extra = sorted(declared - actual)
        if extra:
            reasons.append('Files outside review diff: ' + ', '.join(extra))
    return reasons
