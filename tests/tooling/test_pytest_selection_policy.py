"""Changes to pytest.ini that decide which tests run by default."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.pytest_selection import (
    default_deselected_markers,
    pytest_selection_errors,
)
from tests.support.git_repository import (
    initialize_git_repository,
    run_gate,
    run_git,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
TEST_INTEGRITY = REPOSITORY_ROOT / 'scripts' / 'check_test_integrity.py'
BASE_INI = (
    '[pytest]\ntestpaths = tests\naddopts =\n    -ra\n'
    '    -m "not slow and not perf"\n'
)

pytestmark = pytest.mark.unit


def _with_addopts(*options: str) -> str:
    """Return the base selection with extra ``addopts`` lines."""
    extra = ''.join(f'    {option}\n' for option in options)
    return BASE_INI + extra


@pytest.mark.parametrize(
    'current',
    [
        _with_addopts('--deselect tests/test_value.py::test_value'),
        _with_addopts('--deselect=tests/test_value.py::test_value'),
        _with_addopts('-k "not test_value"'),
        _with_addopts('--ignore=tests/brazil'),
        _with_addopts('--continue-on-collection-errors'),
        _with_addopts('-p no:asyncio'),
        BASE_INI.replace('not perf', 'not perf and not integration'),
        BASE_INI.replace('testpaths = tests', 'testpaths = tests/unit'),
        BASE_INI + 'python_files = check_*.py\n',
    ],
    ids=[
        'deselect',
        'deselect-inline',
        'keyword',
        'ignore',
        'collection-errors',
        'plugin-disabled',
        'marker-expression',
        'testpaths',
        'python-files',
    ],
)
def test_selection_changes_require_a_reason(current: str) -> None:
    """Options that shrink the default run are reviewed like skips."""
    errors = pytest_selection_errors(BASE_INI, current)

    assert errors
    assert all('[TEST_DESELECT]' in error for error in errors)


@pytest.mark.parametrize(
    'current',
    [
        BASE_INI,
        _with_addopts('--strict-markers', '--tb=short'),
        BASE_INI.replace('    -ra\n', ''),
        BASE_INI.replace('    -m "not slow and not perf"\n', ''),
    ],
    ids=['unchanged', 'reporting-options', 'removed-option', 'wider-run'],
)
def test_changes_that_keep_or_widen_the_run_pass(current: str) -> None:
    """Reporting options and wider selections need no justification."""
    assert pytest_selection_errors(BASE_INI, current) == []


def test_an_added_reason_comment_authorizes_a_selection_change() -> None:
    """The reason lives next to the option, as a full-line comment."""
    current = BASE_INI + (
        '    # skip-reason: the Windows runner lacks fork()\n'
        '    --deselect tests/test_value.py::test_fork\n'
    )

    assert pytest_selection_errors(BASE_INI, current) == []


def test_an_unreadable_selection_fails_closed() -> None:
    """A pytest.ini the gate cannot parse is not an approved selection."""
    errors = pytest_selection_errors(BASE_INI, 'addopts = -m "not slow"\n')

    assert len(errors) == 1
    assert '[TEST_POLICY]' in errors[0]


def test_repository_default_selection_is_derived_from_pytest_ini() -> None:
    """The deselected markers come from the canonical pytest selection."""
    pytest_ini = (REPOSITORY_ROOT / 'pytest.ini').read_text(encoding='utf-8')

    assert default_deselected_markers(pytest_ini) == frozenset(
        {'slow', 'perf', 'real_data'}
    )


@pytest.mark.parametrize(
    ('pytest_ini', 'expected'),
    [
        (None, frozenset()),
        ('[pytest]\naddopts = -ra\n', frozenset()),
        ("[pytest]\naddopts = '-m=not slow'\n", frozenset({'slow'})),
    ],
)
def test_default_selection_variants(
    pytest_ini: str | None, expected: frozenset[str]
) -> None:
    """Absent selections deselect nothing; both -m spellings are read."""
    assert default_deselected_markers(pytest_ini) == expected


def test_malformed_pytest_ini_is_rejected() -> None:
    """An unreadable selection must not silently disable the check."""
    with pytest.raises(ValueError, match=r'pytest\.ini'):
        default_deselected_markers('addopts = -m "not slow"\n')


def test_integrity_gate_rejects_a_staged_deselection(tmp_path: Path) -> None:
    """The commit gate reads both pytest.ini snapshots from Git."""
    initialize_git_repository(tmp_path)
    pytest_ini = tmp_path / 'pytest.ini'
    pytest_ini.write_text(BASE_INI, encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'pytest.ini')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')
    pytest_ini.write_text(
        _with_addopts('--deselect tests/test_value.py::test_value'),
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'pytest.ini')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_DESELECT] --deselect' in result.stderr
