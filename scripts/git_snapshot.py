"""Compare the checkout with HEAD and the refs of a push, read-only."""

from __future__ import annotations

from pathlib import Path

from scripts.git_changes import run_git_command


def _root(repo_root: Path | None) -> Path:
    """Return the supplied repository root or the current working directory."""
    return repo_root or Path.cwd()


def _listed_paths(arguments: list[str], repo_root: Path | None) -> list[str]:
    """Run a NUL-delimited Git listing and return its sorted paths."""
    output = run_git_command(
        arguments, _root(repo_root), encoding_errors='surrogateescape'
    ).stdout
    return sorted(path for path in output.split('\0') if path)


def staged_paths_against_head(repo_root: Path | None = None) -> list[str]:
    """Return every staged path whose content differs from HEAD."""
    return _listed_paths(
        ['diff', '--cached', '--name-only', '-z', 'HEAD', '--'], repo_root
    )


def unstaged_paths(repo_root: Path | None = None) -> list[str]:
    """Return every tracked path whose working-tree copy differs."""
    return _listed_paths(['diff', '--name-only', '-z', '--'], repo_root)


def untracked_paths(repo_root: Path | None = None) -> list[str]:
    """Return untracked paths that Git does not ignore."""
    return _listed_paths(
        ['ls-files', '--others', '--exclude-standard', '-z'], repo_root
    )


def ignored_paths(
    pathspecs: list[str],
    repo_root: Path | None = None,
    *,
    collapse_directories: bool = False,
) -> list[str]:
    """Return untracked paths that Git ignores within the pathspecs.

    With ``collapse_directories``, an ignored directory is listed once, with a
    trailing slash, instead of being walked.
    """
    arguments = ['ls-files', '--others', '--ignored', '--exclude-standard']
    if collapse_directories:
        arguments.append('--directory')
    return _listed_paths([*arguments, '-z', '--', *pathspecs], repo_root)


def git_path(name: str, repo_root: Path | None = None) -> Path:
    """Return where Git keeps ``name``, honoring worktrees and hook paths."""
    root = _root(repo_root)
    location = run_git_command(['rev-parse', '--git-path', name], root).stdout
    return root / location.strip()


def commit_exists(revision: str, repo_root: Path | None = None) -> bool:
    """Return whether a revision names a commit in the local repository."""
    result = run_git_command(
        ['cat-file', '-e', f'{revision}^{{commit}}'],
        _root(repo_root),
        check=False,
    )
    return result.returncode == 0


def has_commits_outside(
    commit: str,
    excluded: list[str],
    remote: str,
    repo_root: Path | None = None,
) -> bool:
    """Return whether ``commit`` reaches commits the remote does not have.

    The remote's commits are those of its remote-tracking branches plus any
    ``excluded`` revision, such as the remote ref's current value.
    """
    result = run_git_command(
        [
            'rev-list',
            '--max-count=1',
            commit,
            '--not',
            f'--remotes={remote}',
            *excluded,
        ],
        _root(repo_root),
    )
    return bool(result.stdout.strip())


def _differs_from_index(path: str, root: Path) -> bool:
    """Return whether a working-tree file differs from its index blob."""
    entry = run_git_command(
        ['ls-files', '--stage', '-z', '--', path],
        root,
        encoding_errors='surrogateescape',
    ).stdout
    fields = entry.split(maxsplit=2)
    if len(fields) < 2 or not (root / path).is_file():
        return True
    current = run_git_command(['hash-object', '--', path], root).stdout.strip()
    return current != fields[1]


def hidden_index_changes(repo_root: Path | None = None) -> list[str]:
    """Return flagged paths whose working copy differs from the index.

    ``assume-unchanged`` and ``skip-worktree`` entries make ``git diff`` skip
    a file, so their content is compared with the index blob directly.
    """
    root = _root(repo_root)
    listing = run_git_command(
        ['ls-files', '-v', '-z'], root, encoding_errors='surrogateescape'
    ).stdout
    flagged = [
        path
        for tag, _, path in (
            entry.partition(' ') for entry in listing.split('\0')
        )
        if path and (tag.islower() or tag == 'S')
    ]
    return sorted(path for path in flagged if _differs_from_index(path, root))
