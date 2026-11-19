"""AST detection of constructs that keep tests out of the default run."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.skip_signals import added_signal_errors
from tests.support.git_repository import (
    initialize_git_repository,
    run_gate,
    run_git,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
TEST_INTEGRITY = REPOSITORY_ROOT / 'scripts' / 'check_test_integrity.py'
DESELECTED = frozenset({'slow', 'perf', 'real_data'})
HEADER = 'import unittest\n\nimport pytest\n\n\n'
BASE = HEADER + 'def test_value() -> None:\n    assert 1 == 1\n'
PARAMETRIZED = (
    HEADER + "@pytest.mark.parametrize('value', [1, 2])\n"
    'def test_value(value: int) -> None:\n    assert value > 0\n'
)
SKIPIF_TEST = (
    HEADER + "@pytest.mark.skipif(True, reason='flaky')\n"
    'def test_value() -> None:\n    assert 1 == 1\n'
)
SLOW_TEST = (
    HEADER
    + '@pytest.mark.slow\ndef test_value() -> None:\n    assert 1 == 1\n'
)
PARAM_SKIP_TEST = PARAMETRIZED.replace(
    '[1, 2]',
    "[1, pytest.param(2, marks=pytest.mark.skipif(True, reason='x'))]",
)
IMPORTED_SKIP_TEST = (
    'from unittest import skip\n\n\n'
    "@skip('later')\ndef test_value() -> None:\n    assert 1 == 1\n"
)

pytestmark = pytest.mark.unit


def _errors(source: str, base: str | None = BASE) -> list[str]:
    """Inspect one module change with the repository's deselected markers."""
    return added_signal_errors('tests/test_value.py', base, source, DESELECTED)


def _in_test(statement: str) -> str:
    """Insert one statement at the start of the baseline test body."""
    return BASE.replace('    assert', f'    {statement}\n    assert')


@pytest.mark.parametrize(
    ('source', 'code'),
    [
        (SKIPIF_TEST, '[TEST_SKIP]'),
        (_in_test("pytest.skip('later')"), '[TEST_SKIP]'),
        (_in_test("pytest.xfail('later')"), '[TEST_SKIP]'),
        (BASE + '\npytestmark = pytest.mark.skip\n', '[TEST_SKIP]'),
        (
            BASE + '\npytestmark = [pytest.mark.unit, pytest.mark.xfail]\n',
            '[TEST_SKIP]',
        ),
        (BASE + "\npytest.importorskip('numpy')\n", '[TEST_SKIP]'),
        (
            BASE + "\n\n@unittest.skip('later')\nclass TestValue:\n"
            '    def test_case(self) -> None:\n        assert True\n',
            '[TEST_SKIP]',
        ),
        (
            BASE + '\n\nclass TestCase(unittest.TestCase):\n'
            '    def test_case(self) -> None:\n'
            "        self.skipTest('later')\n",
            '[TEST_SKIP]',
        ),
        (SLOW_TEST, '[TEST_DESELECT]'),
        (
            BASE + '\n\nclass TestHeavy:\n    pytestmark = pytest.mark.perf\n',
            '[TEST_DESELECT]',
        ),
        (PARAM_SKIP_TEST, '[TEST_SKIP]'),
        (
            PARAMETRIZED.replace(
                '[1, 2]', '[1, pytest.param(2, marks=[pytest.mark.slow])]'
            ),
            '[TEST_DESELECT]',
        ),
        (IMPORTED_SKIP_TEST, '[TEST_SKIP]'),
        (
            'from unittest import skipIf as when\n\n\n'
            "@when(True, 'later')\ndef test_value() -> None:\n"
            '    assert 1 == 1\n',
            '[TEST_SKIP]',
        ),
        (
            'from unittest import SkipTest\n\n\n'
            "def test_value() -> None:\n    raise SkipTest('later')\n",
            '[TEST_SKIP]',
        ),
        (_in_test("raise unittest.SkipTest('later')"), '[TEST_SKIP]'),
        (_in_test('raise unittest.SkipTest'), '[TEST_SKIP]'),
        (_in_test("raise pytest.skip.Exception('later')"), '[TEST_SKIP]'),
        (
            'import pytest as pt\n\n\n'
            '@pt.mark.skip\ndef test_value() -> None:\n    assert 1 == 1\n',
            '[TEST_SKIP]',
        ),
        (
            'from pytest import mark\n\n\n'
            '@mark.slow\ndef test_value() -> None:\n    assert 1 == 1\n',
            '[TEST_DESELECT]',
        ),
        (
            BASE.replace(
                'def test_value', '@ pytest.mark.skip\ndef test_value'
            ),
            '[TEST_SKIP]',
        ),
        (
            BASE.replace('() -> None:', '(request) -> None:').replace(
                '    assert',
                "    request.applymarker(pytest.mark.xfail(reason='x'))\n"
                '    assert',
            ),
            '[TEST_SKIP]',
        ),
        (_in_test("check = lambda: pytest.skip('later')"), '[TEST_SKIP]'),
    ],
    ids=[
        'skipif-marker',
        'skip-call',
        'xfail-call',
        'module-pytestmark',
        'pytestmark-list',
        'importorskip',
        'unittest-decorator',
        'skiptest-call',
        'deselected-marker',
        'class-pytestmark',
        'parameter-skipif',
        'parameter-deselected-marker',
        'imported-unittest-skip',
        'aliased-unittest-skipif',
        'imported-skiptest-exception',
        'unittest-skiptest-exception',
        'unittest-skiptest-class',
        'pytest-skip-exception',
        'aliased-pytest-module',
        'imported-pytest-mark',
        'decorator-outside-line-gate',
        'applied-marker',
        'skip-inside-lambda',
    ],
)
def test_added_constructs_require_a_reason(source: str, code: str) -> None:
    """Every way a test stops running by default is reported."""
    errors = _errors(source)

    assert len(errors) == 1, errors
    assert code in errors[0]
    assert errors[0].startswith('tests/test_value.py:')


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ("collect_ignore = ['test_a.py', 'test_b.py']\n", 2),
        ("collect_ignore_glob = ['legacy/*.py']\n", 1),
        ("collect_ignore.append('test_a.py')\n", 1),
        ("collect_ignore.extend(['test_a.py', 'test_b.py'])\n", 2),
        ("collect_ignore += ['test_a.py']\n", 1),
        ('def pytest_collection_modifyitems(config, items):\n    pass\n', 1),
        ('def pytest_ignore_collect(collection_path):\n    return\n', 1),
        ('def hook(config, items):\n    config.hook.pytest_deselected()\n', 1),
    ],
    ids=[
        'collect-ignore-list',
        'collect-ignore-glob',
        'collect-ignore-append',
        'collect-ignore-extend',
        'collect-ignore-augmented',
        'modifyitems-hook',
        'ignore-collect-hook',
        'deselected-hook-call',
    ],
)
def test_collection_changes_require_a_reason(
    source: str, expected: int
) -> None:
    """Each removed collection entry or deselection hook is a signal."""
    errors = added_signal_errors('tests/conftest.py', '', source, frozenset())

    assert len(errors) == expected, errors
    assert all('[TEST_DESELECT]' in error for error in errors)


def test_a_new_collect_ignore_entry_is_reported() -> None:
    """Extending an existing ignore list needs its own reason."""
    base = "collect_ignore = ['test_a.py']\n"
    source = "collect_ignore = ['test_a.py', 'test_b.py']\n"

    errors = added_signal_errors('conftest.py', base, source, frozenset())

    assert len(errors) == 1


@pytest.mark.parametrize(
    ('base', 'use'),
    [
        (
            HEADER + 'SLOW = pytest.mark.slow  # skip-reason: shared tier\n',
            '\n\n@SLOW\ndef test_value() -> None:\n    assert 1\n',
        ),
        (
            HEADER + 'class TestValue:\n'
            '    SLOW = pytest.mark.slow  # skip-reason: shared tier\n',
            '\n    @SLOW\n    def test_value(self) -> None:\n'
            '        assert 1\n',
        ),
    ],
    ids=['module-alias', 'class-alias'],
)
def test_each_use_of_a_marker_alias_is_reported(base: str, use: str) -> None:
    """A reviewed alias does not authorize new deselected tests."""
    errors = _errors(base + use, base=base)

    assert len(errors) == 1
    assert '[TEST_DESELECT] pytest.mark.slow' in errors[0]


def test_a_new_test_cannot_bypass_deselection_by_renaming() -> None:
    """A deselected replacement test needs the same justification."""
    renamed = SLOW_TEST.replace('test_value', 'test_value_v2')

    assert any('[TEST_DESELECT]' in error for error in _errors(renamed))


def test_a_reason_on_the_construct_line_authorizes_it() -> None:
    """The documented skip-reason convention keeps intent reviewable."""
    justified = SKIPIF_TEST.replace(
        "reason='flaky')", "reason='flaky')  # skip-reason: POSIX shell only"
    )

    assert _errors(justified) == []


def test_a_reason_on_the_parameter_line_authorizes_it() -> None:
    """Parameter marks take their reason on their own source line."""
    justified = PARAM_SKIP_TEST.replace(
        '])\n', '])  # skip-reason: needs a POSIX shell\n', 1
    )

    assert _errors(justified, base=PARAMETRIZED) == []


def test_unchanged_constructs_are_not_reported() -> None:
    """Existing, already reviewed constructs stay valid."""
    edited = SKIPIF_TEST.replace('assert 1 == 1', 'assert 2 == 2')

    assert _errors(edited, base=SKIPIF_TEST) == []


def test_each_added_occurrence_needs_its_own_reason() -> None:
    """A second skip call is new even when the base had one."""
    one_skip = _in_test("pytest.skip('a')")
    two_skips = one_skip.replace(
        "    pytest.skip('a')", "    pytest.skip('a')\n    pytest.skip('b')"
    )

    assert len(_errors(two_skips, base=one_skip)) == 1


CHANGED_CONSTRUCTS = [
    pytest.param(
        HEADER + "@pytest.mark.skipif(False, reason='x')  # skip-reason: R\n"
        'def test_value() -> None:\n    assert 1 == 1\n',
        ('False', 'True'),
        id='marker-condition',
    ),
    pytest.param(
        HEADER + "@unittest.skipIf(False, 'x')  # skip-reason: R\n"
        'def test_value() -> None:\n    assert 1 == 1\n',
        ('False', 'True'),
        id='unittest-condition',
    ),
    pytest.param(
        "collect_ignore = ['test_a.py']  # skip-reason: R\n",
        ('test_a.py', 'test_b.py'),
        id='collect-ignore-target',
    ),
    pytest.param(
        HEADER + 'ONLINE = True\n\n\ndef test_value() -> None:\n'
        '    if not ONLINE:\n'
        "        pytest.skip('offline')  # skip-reason: R\n"
        '    assert 1 == 1\n',
        ('if not ONLINE', 'if ONLINE'),
        id='enclosing-condition',
    ),
    pytest.param(
        HEADER + 'NEEDS_GPU = False\n\n\n'
        "@pytest.mark.skipif(NEEDS_GPU, reason='x')  # skip-reason: R\n"
        'def test_value() -> None:\n    assert 1 == 1\n',
        ('NEEDS_GPU = False', 'NEEDS_GPU = True'),
        id='module-value',
    ),
    pytest.param(
        HEADER + 'try:\n    import json\nexcept ImportError:\n'
        "    pytest.skip('x', allow_module_level=True)  # skip-reason: R\n",
        ('except ImportError', 'except Exception'),
        id='except-clause',
    ),
    pytest.param(
        HEADER + 'pytestmark = pytest.mark.skip if False else []'
        '  # skip-reason: R\n',
        ('if False', 'if True'),
        id='conditional-expression',
    ),
]


@pytest.mark.parametrize(('base', 'change'), CHANGED_CONSTRUCTS)
def test_a_changed_construct_without_a_reason_is_reported(
    base: str, change: tuple[str, str]
) -> None:
    """Changing what a reviewed construct does is a new construct."""
    changed = base.replace(*change).replace('  # skip-reason: R', '')

    errors = _errors(changed, base=base)

    assert len(errors) == 1, errors
    assert 'add "skip-reason: <why>"' in errors[0]


@pytest.mark.parametrize(('base', 'change'), CHANGED_CONSTRUCTS)
def test_a_changed_construct_cannot_keep_its_old_reason(
    base: str, change: tuple[str, str]
) -> None:
    """The reason given for the old construct does not cover the new one."""
    changed = base.replace(*change).replace(
        'skip-reason: R', 'skip-reason: r '
    )

    errors = _errors(changed, base=base)

    assert len(errors) == 1, errors
    assert 'keeps a reason the base already gave' in errors[0]


@pytest.mark.parametrize(('base', 'change'), CHANGED_CONSTRUCTS)
def test_a_changed_construct_with_a_new_reason_passes(
    base: str, change: tuple[str, str]
) -> None:
    """A reason written for the change authorizes it."""
    changed = base.replace(*change).replace('skip-reason: R', 'skip-reason: S')

    assert _errors(changed, base=base) == []


def test_an_alias_change_is_reported_once_where_it_is_defined() -> None:
    """Uses of a changed marker alias are not reported again."""
    base = (
        HEADER + "GATED = pytest.mark.skipif(False, reason='x')"
        '  # skip-reason: R\n\n\n'
        '@GATED  # skip-reason: uses the gate\n'
        'def test_value() -> None:\n    assert 1 == 1\n'
    )

    errors = _errors(base.replace('(False', '(True'), base=base)

    assert len(errors) == 1, errors
    assert errors[0].startswith('tests/test_value.py:6:')


def test_moving_or_reformatting_a_construct_keeps_its_identity() -> None:
    """Position, layout, and the surrounding test body do not matter."""
    base = _in_test("pytest.skip('a')")
    edited = base.replace("    pytest.skip('a')\n", '').replace(
        'assert 1 == 1', 'assert 2 == 2\n    pytest.skip(\n        "a"\n    )'
    )

    assert _errors(edited, base=base) == []


def test_a_renamed_test_keeps_its_reason() -> None:
    """A reason on the construct's line still applies after a rename."""
    justified = SKIPIF_TEST.replace(
        "reason='flaky')", "reason='flaky')  # skip-reason: POSIX shell only"
    )

    renamed = justified.replace('test_value', 'test_value_v2')

    assert _errors(renamed, base=justified) == []


def test_decorator_skip_and_xfail_belong_to_the_line_gate() -> None:
    """The line-based gate already reports these decorators once."""
    for marker in ('skip', 'xfail'):
        decorated = BASE.replace(
            'def test_value', f'@pytest.mark.{marker}\ndef test_value'
        )

        assert _errors(decorated) == []


@pytest.mark.parametrize(
    'statement',
    [
        "message = 'pytest.mark.skip is documented here'",
        'value = pytest.approx(1.0)',
        'from unittest import mock',
        'expected = pytest.raises(pytest.skip.Exception)',
        'expected = pytest.raises(unittest.SkipTest)',
        'kinds = (unittest.SkipTest, pytest.xfail.Exception)',
    ],
    ids=[
        'string',
        'other-pytest-helper',
        'other-unittest-module',
        'expected-pytest-skip',
        'expected-unittest-skip',
        'exception-tuple',
    ],
)
def test_unrelated_references_are_not_reported(statement: str) -> None:
    """Strings, other helpers, and expected skip exceptions are not signals.

    Catching or expecting a skip exception verifies a skip elsewhere; only
    raising one stops the running test.
    """
    assert _errors(_in_test(statement)) == []


def test_raising_an_aliased_skip_exception_is_reported() -> None:
    """An alias of a skip exception skips the test once it is raised."""
    source = (
        HEADER + 'Skip = unittest.SkipTest\n\n\n'
        "def test_value() -> None:\n    raise Skip('later')\n"
    )

    errors = _errors(source)

    assert len(errors) == 1
    assert '[TEST_SKIP] unittest.SkipTest' in errors[0]


def test_a_new_module_is_compared_with_an_empty_base() -> None:
    """Constructs in a brand-new test module are all additions."""
    assert any('[TEST_SKIP]' in error for error in _errors(SKIPIF_TEST, None))


def test_an_unparsable_module_fails_closed() -> None:
    """A module the gate cannot inspect is not an approved module."""
    errors = _errors(BASE + 'def broken(:\n')

    assert len(errors) == 1
    assert '[TEST_PARSE]' in errors[0]


def _repository_with_test(repo: Path, source: str = BASE) -> Path:
    """Commit a pytest selection and one test module."""
    initialize_git_repository(repo)
    (repo / 'pytest.ini').write_text(
        '[pytest]\naddopts = -m "not slow"\n', encoding='utf-8'
    )
    test_file = repo / 'tests' / 'test_value.py'
    test_file.parent.mkdir()
    test_file.write_text(source, encoding='utf-8')
    run_git(repo, 'add', '--', 'pytest.ini', 'tests/test_value.py')
    run_git(repo, 'commit', '--quiet', '-m', 'baseline')
    return test_file


@pytest.mark.parametrize(
    ('base', 'source', 'code'),
    [
        (BASE, SKIPIF_TEST, '[TEST_SKIP]'),
        (BASE, SLOW_TEST, '[TEST_DESELECT]'),
        (PARAMETRIZED, PARAM_SKIP_TEST, '[TEST_SKIP]'),
        (BASE, IMPORTED_SKIP_TEST, '[TEST_SKIP]'),
    ],
    ids=['skipif', 'deselected', 'parameter-skipif', 'imported-skip'],
)
def test_integrity_gate_rejects_staged_constructs(
    tmp_path: Path, base: str, source: str, code: str
) -> None:
    """The commit gate inspects the staged snapshot."""
    test_file = _repository_with_test(tmp_path, base)
    test_file.write_text(source, encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'tests/test_value.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert code in result.stderr


def test_integrity_gate_inspects_a_root_conftest(tmp_path: Path) -> None:
    """A conftest outside tests/ can still remove tests from collection."""
    _repository_with_test(tmp_path)
    (tmp_path / 'conftest.py').write_text(
        "collect_ignore = ['tests/test_value.py']\n", encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'conftest.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_DESELECT] collect_ignore' in result.stderr


def test_integrity_gate_accepts_a_justified_staged_construct(
    tmp_path: Path,
) -> None:
    """A reviewed reason on the marker line passes the commit gate."""
    test_file = _repository_with_test(tmp_path)
    test_file.write_text(
        SLOW_TEST.replace(
            '@pytest.mark.slow', '@pytest.mark.slow  # skip-reason: 15k rows'
        ),
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_value.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ('base', 'source'),
    [(BASE, SKIPIF_TEST), (PARAMETRIZED, PARAM_SKIP_TEST)],
    ids=['skipif', 'parameter-skipif'],
)
def test_integrity_gate_rejects_constructs_in_a_commit_range(
    tmp_path: Path, base: str, source: str
) -> None:
    """CI inspects the same constructs in its cumulative range."""
    test_file = _repository_with_test(tmp_path, base)
    test_file.write_text(source, encoding='utf-8')
    run_git(tmp_path, 'commit', '--quiet', '-am', 'skip the test')

    result = run_gate(TEST_INTEGRITY, tmp_path, '--range', 'HEAD~1..HEAD')

    assert result.returncode == 1
    assert '[TEST_SKIP]' in result.stderr
