"""Real `git push` runs through the installed pre-commit pre-push hook."""

from __future__ import annotations

import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.git_snapshot import git_path
from scripts.process_runner import ProcessResult
from tests.support.git_repository import initialize_git_repository, run_git
from tests.support.installed_hooks import (
    install_local_hooks,
    run_with_hooks,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
PUSH_SNAPSHOT = REPOSITORY_ROOT / 'scripts' / 'check_push_snapshot.py'
PAUSE_TIMEOUT = 60
PAUSE = f"""import os
import sys
import time
from pathlib import Path

markers = Path(sys.argv[1])
remote = os.environ['PRE_COMMIT_REMOTE_NAME']
(markers / f'{{remote}}.entered').write_text('entered', encoding='utf-8')
deadline = time.monotonic() + {PAUSE_TIMEOUT}
while not (markers / f'{{remote}}.release').exists():
    if time.monotonic() > deadline:
        sys.exit(3)
    time.sleep(0.02)
"""

pytestmark = pytest.mark.integration


def _pushing_repository(
    tmp_path: Path, *, pause: Path | None = None
) -> tuple[Path, Path]:
    """Create a repository whose pre-push hooks run only the guard.

    With ``pause``, a hook ahead of the guard waits for a release marker in
    that directory, so a test can interleave concurrent pushes.
    """
    repo, home = tmp_path / 'work', tmp_path / 'pre-commit'
    repo.mkdir()
    initialize_git_repository(repo)
    hooks: list[tuple[str, list[str]]] = []
    if pause is not None:
        script = tmp_path / 'pause.py'
        script.write_text(PAUSE, encoding='utf-8')
        hooks.append(('pause', [sys.executable, str(script), str(pause)]))
    hooks.append(('push-snapshot', [sys.executable, str(PUSH_SNAPSHOT)]))
    install_local_hooks(repo, home, stage='pre-push', hooks=hooks)
    (repo / '.gitignore').write_text('local_settings.py\n', encoding='utf-8')
    (repo / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    run_git(repo, 'add', '--', '.pre-commit-config.yaml', '.gitignore')
    run_git(repo, 'add', '--', 'module.py')
    run_git(repo, 'commit', '--quiet', '-m', 'baseline')
    validator = run_with_hooks(
        repo, home, 'python', str(PUSH_SNAPSHOT), '--install'
    )
    assert validator.returncode == 0, validator.stderr
    return repo, home


def _remote(repo: Path, name: str) -> Path:
    """Add an empty bare remote to a repository and return its path."""
    remote = repo.parent / f'{name}.git'
    run_git(repo.parent, 'init', '--quiet', '--bare', str(remote))
    run_git(repo, 'remote', 'add', name, str(remote))
    return remote


def _unvalidated_commit(repo: Path) -> None:
    """Commit a change on branch ``review-bad`` and switch back."""
    run_git(repo, 'switch', '--quiet', '-c', 'review-bad')
    (repo / 'module.py').write_text('VALUE = 2\n', encoding='utf-8')
    run_git(repo, 'commit', '--quiet', '-am', 'unvalidated change')
    run_git(repo, 'switch', '--quiet', '-')


def _remote_refs(remote: Path) -> set[str]:
    """Return the refs a bare remote received."""
    listing = run_git(remote, 'for-each-ref', '--format=%(refname)')
    return set(listing.stdout.split())


def _output(result: ProcessResult) -> str:
    """Return everything a push printed."""
    return result.stdout + result.stderr


@pytest.fixture
def pushing_repository(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a repository with an empty remote named ``review``."""
    repo, home = _pushing_repository(tmp_path)
    return repo, _remote(repo, 'review'), home


def test_a_multi_ref_push_of_another_commit_is_rejected(
    pushing_repository: tuple[Path, Path, Path],
) -> None:
    """The second ref is validated even though pre-commit selects the first."""
    repo, remote, home = pushing_repository
    _unvalidated_commit(repo)

    result = run_with_hooks(
        repo,
        home,
        'git',
        'push',
        'review',
        'HEAD:refs/heads/aaa-current',
        'review-bad:refs/heads/zzz-other',
    )

    assert result.returncode != 0
    assert 'FAIL [PUSH_SNAPSHOT]' in _output(result)
    assert 'refs/heads/zzz-other publishes' in _output(result)
    assert _remote_refs(remote) == set()


def test_a_multi_ref_push_of_the_checkout_is_published(
    pushing_repository: tuple[Path, Path, Path],
) -> None:
    """Several refs that all point at the clean checkout are accepted."""
    repo, remote, home = pushing_repository

    result = run_with_hooks(
        repo,
        home,
        'git',
        'push',
        'review',
        'HEAD:refs/heads/aaa-current',
        'HEAD:refs/heads/zzz-copy',
    )

    assert result.returncode == 0, _output(result)
    assert 'PUSH_SNAPSHOT' not in result.stderr
    assert _remote_refs(remote) == {
        'refs/heads/aaa-current',
        'refs/heads/zzz-copy',
    }


def test_an_ignored_python_dependency_blocks_the_push(
    pushing_repository: tuple[Path, Path, Path],
) -> None:
    """An ignored module the checkout could import is not in the commit."""
    repo, remote, home = pushing_repository
    helper = repo / 'src' / 'pkg' / 'local_settings.py'
    helper.parent.mkdir(parents=True)
    helper.write_text('TOKEN = 1\n', encoding='utf-8')

    result = run_with_hooks(
        repo, home, 'git', 'push', 'review', 'HEAD:refs/heads/x'
    )

    assert result.returncode != 0
    assert 'src/pkg/local_settings.py' in _output(result)
    assert _remote_refs(remote) == set()


def test_a_push_without_the_validator_is_rejected(
    pushing_repository: tuple[Path, Path, Path],
) -> None:
    """Removing the validator fails closed instead of checking one ref."""
    repo, remote, home = pushing_repository
    git_path('hooks/pre-push.legacy', repo).unlink()

    result = run_with_hooks(
        repo, home, 'git', 'push', 'review', 'HEAD:refs/heads/x'
    )

    assert result.returncode != 0
    assert 'scripts/check_push_snapshot.py --install' in _output(result)
    assert _remote_refs(remote) == set()


def _wait_for(marker: Path, push: Future[ProcessResult]) -> None:
    """Wait until a paused push reaches its hooks.

    Raises:
        AssertionError: If the push ends or stalls before reaching the pause.
    """
    deadline = time.monotonic() + PAUSE_TIMEOUT
    while not marker.exists():
        if push.done():
            raise AssertionError(_output(push.result()))
        if time.monotonic() > deadline:
            raise AssertionError(f'{marker.name} was never written')
        time.sleep(0.02)


def test_concurrent_pushes_keep_their_own_ref_lists(tmp_path: Path) -> None:
    """A push cannot pass with the ref list of a push that ran meanwhile.

    Push A publishes HEAD and an unvalidated commit; push B publishes only
    HEAD. Both validators finish before either guard starts and A's guard
    runs first: with a shared record, A read B's list and published both.
    """
    markers = tmp_path / 'markers'
    markers.mkdir()
    repo, home = _pushing_repository(tmp_path, pause=markers)
    review, shadow = _remote(repo, 'review'), _remote(repo, 'shadow')
    _unvalidated_commit(repo)

    with ThreadPoolExecutor(max_workers=2) as pushes:
        push_a = pushes.submit(
            run_with_hooks,
            repo,
            home,
            'git',
            'push',
            'review',
            'HEAD:refs/heads/validated',
            'review-bad:refs/heads/unvalidated',
        )
        _wait_for(markers / 'review.entered', push_a)
        push_b = pushes.submit(
            run_with_hooks,
            repo,
            home,
            'git',
            'push',
            'shadow',
            'HEAD:refs/heads/validated',
        )
        _wait_for(markers / 'shadow.entered', push_b)
        (markers / 'review.release').write_text('go', encoding='utf-8')
        result_a = push_a.result()
        (markers / 'shadow.release').write_text('go', encoding='utf-8')
        result_b = push_b.result()

    assert result_a.returncode != 0
    assert 'refs/heads/unvalidated publishes' in _output(result_a)
    assert _remote_refs(review) == set()
    assert result_b.returncode == 0, _output(result_b)
    assert _remote_refs(shadow) == {'refs/heads/validated'}
