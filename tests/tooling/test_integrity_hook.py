"""Real `git commit` runs through the installed test-integrity hook."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.git_repository import initialize_git_repository, run_git
from tests.support.installed_hooks import install_local_hook, run_with_hooks

REPOSITORY_ROOT = Path(__file__).parents[2]
TEST_INTEGRITY = REPOSITORY_ROOT / 'scripts' / 'check_test_integrity.py'
TEST_MODULE = 'tests/test_value.py'
BASELINE = (
    'import pytest\n\n\n'
    "@pytest.mark.parametrize('value', [1, 2])\n"
    'def test_value(value: int) -> None:\n'
    '    assert value > 0\n'
)
REVIEWED_SKIP = (
    'import pytest\n\n\n'
    "@pytest.mark.skipif(False, reason='x')  # skip-reason: POSIX only\n"
    'def test_value() -> None:\n'
    '    assert True\n'
)
REVIEWED_IGNORE = "collect_ignore = ['test_a.py']  # skip-reason: legacy\n"

pytestmark = pytest.mark.integration


def _committing_repository(
    tmp_path: Path, path: str, source: str
) -> tuple[Path, Path]:
    """Commit one module through a commit hook that runs only the gate."""
    repo, home = tmp_path / 'work', tmp_path / 'pre-commit'
    repo.mkdir()
    initialize_git_repository(repo)
    install_local_hook(
        repo,
        home,
        hook_id='test-integrity',
        script=TEST_INTEGRITY,
        stage='pre-commit',
    )
    (repo / 'pytest.ini').write_text(
        '[pytest]\n# skip-reason: slow tests are opt-in\n'
        'addopts = -m "not slow"\n',
        encoding='utf-8',
    )
    module = repo / path
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(source, encoding='utf-8')
    run_git(repo, 'add', '--', '.pre-commit-config.yaml', 'pytest.ini')
    run_git(repo, 'add', '--', path)
    baseline = run_with_hooks(
        repo, home, 'git', 'commit', '--quiet', '-m', 'baseline'
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    return repo, home


def _commit_change(
    repo: Path, home: Path, path: str, source: str
) -> tuple[int, str]:
    """Stage a new version of one module, commit it, and report the result."""
    (repo / path).write_text(source, encoding='utf-8')
    run_git(repo, 'add', '--', path)
    result = run_with_hooks(
        repo, home, 'git', 'commit', '--quiet', '-m', 'change the module'
    )
    return result.returncode, result.stdout + result.stderr


def _commit_count(repo: Path) -> str:
    """Return how many commits HEAD has."""
    return run_git(repo, 'rev-list', '--count', 'HEAD').stdout.strip()


@pytest.mark.parametrize(
    ('source', 'label'),
    [
        (
            BASELINE.replace(
                '[1, 2]',
                '[1, pytest.param(2, marks=pytest.mark.skipif(True, '
                "reason='x'))]",
            ),
            'pytest.mark.skipif',
        ),
        (
            'from unittest import skip\n\n'
            + BASELINE.replace(
                'def test_value', "@skip('later')\ndef test_value"
            ),
            'unittest.skip',
        ),
    ],
    ids=['parameter-skipif', 'imported-unittest-skip'],
)
def test_an_unreasoned_skip_cannot_be_committed(
    tmp_path: Path, source: str, label: str
) -> None:
    """The installed hook stops the commit, so the skip never lands."""
    repo, home = _committing_repository(tmp_path, TEST_MODULE, BASELINE)

    returncode, output = _commit_change(repo, home, TEST_MODULE, source)

    assert returncode != 0
    assert f'[TEST_SKIP] {label}' in output
    assert _commit_count(repo) == '1'


@pytest.mark.parametrize(
    ('path', 'base', 'change', 'comment', 'accepted'),
    [
        (TEST_MODULE, REVIEWED_SKIP, ('False', 'True'), None, False),
        (TEST_MODULE, REVIEWED_SKIP, ('False', 'True'), 'POSIX only', False),
        (TEST_MODULE, REVIEWED_SKIP, ('False', 'True'), 'until #12', True),
        ('conftest.py', REVIEWED_IGNORE, ('_a.', '_b.'), 'legacy', False),
    ],
    ids=[
        'skipif-reason-removed',
        'skipif-reason-kept',
        'skipif-reason-renewed',
        'ignore-target-reason-kept',
    ],
)
def test_changing_a_reviewed_construct_needs_a_new_reason(
    tmp_path: Path,
    path: str,
    base: str,
    change: tuple[str, str],
    comment: str | None,
    accepted: bool,
) -> None:
    """A construct whose condition or target changed is reviewed again."""
    repo, home = _committing_repository(tmp_path, path, base)
    start = base.index('  # skip-reason:')
    old_comment = base[start : base.index('\n', start)]
    new_comment = '' if comment is None else f'  # skip-reason: {comment}'
    changed = base.replace(*change).replace(old_comment, new_comment)

    returncode, output = _commit_change(repo, home, path, changed)

    if accepted:
        assert returncode == 0, output
        assert _commit_count(repo) == '2'
    else:
        assert returncode != 0
        assert 'added or changed in' in output
        assert _commit_count(repo) == '1'
