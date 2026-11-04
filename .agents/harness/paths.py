"""Root resolution for harness tooling.

A harness script reads its own content — skills, agent definitions,
workflows, schema — from *this* repository, and reads or writes project
artifacts in whatever repository the operator is standing in. Those are two
different roots. Deriving both from ``__file__`` only works while the
harness lives inside the consuming repository, which is no longer the case.

Scripts bootstrap this module by putting the harness root on ``sys.path``:

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from harness.paths import HARNESS_ROOT, repo_root
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]


def content_root(name: str) -> Path:
    """Return the source root for one harness content type.

    The three fan-out scripts read their canonical sources from here. When
    the operated repository holds a published projection lock at
    ``.agents/harness.lock.json``, every content type resolves to the
    projection: ``repo_root()/.agents/<name>``, whether or not that subtree
    exists on disk — a missing subtree means the consumer selected nothing
    of that type. Without a lock the installed harness root is the source.

    The decision is the lock file alone; nothing here reads or interprets
    the lock's content, the manifest or the catalog. ``harness/selection``
    and ``harness/projection`` never call this function: they always read
    component sources from the installed distribution.
    """
    root = repo_root()
    if (root / '.agents' / 'harness.lock.json').is_file():
        return root / '.agents' / name
    return HARNESS_ROOT / name


def strict_repo_root(cwd: Path | str | None = None) -> Path:
    """Return the repository root for cwd or fail strictly.

    Unlike repo_root(), this function never falls back to cwd. It requires
    git rev-parse --show-toplevel to succeed with a non-empty resolved path.
    """
    working_dir = Path(cwd) if cwd is not None else Path.cwd()
    try:
        completed = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitRootError(
            f'not inside a git repository or git unavailable: {working_dir}'
        ) from exc

    resolved = completed.stdout.strip()
    if not resolved:
        raise GitRootError(
            f'git rev-parse --show-toplevel returned empty root: {working_dir}'
        )
    return Path(resolved).resolve()


class GitRootError(Exception):
    """Strict Git root could not be determined."""


def repo_root() -> Path:
    """Return the repository the operator is acting on.

    Resolved from the working directory, never from this file's location, so
    the same harness serves every consuming repository. Falls back to the
    working directory when git is unavailable or the cwd is not a checkout.

    Deliberately uncached: callers change directory between invocations, and
    a cached first answer would silently pin every later lookup to whichever
    directory happened to ask first.
    """
    try:
        completed = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()

    resolved = completed.stdout.strip()
    return Path(resolved) if resolved else Path.cwd()
