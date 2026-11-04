"""Tests for the structural test-quality checker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
CHECKER_PATH = REPOSITORY_ROOT / 'scripts' / 'check_test_quality.py'

pytestmark = pytest.mark.unit


@pytest.fixture
def checker(monkeypatch: pytest.MonkeyPatch):
    """Load the checker without importing the repository test suite."""
    monkeypatch.syspath_prepend(str(REPOSITORY_ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location(
        'check_test_quality', CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError('Unable to load check_test_quality.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def inspect_source(checker, tmp_path: Path, source: str):
    """Write and inspect one temporary test module."""
    path = tmp_path / 'test_sample.py'
    path.write_text(source, encoding='utf-8')
    return path, checker.inspect_test_file(path)


def test_marker_inheritance_accepts_one_primary_and_additive_qualifiers(
    checker, tmp_path: Path
) -> None:
    """Module, class, and function markers compose predictably."""
    source = """
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

class TestLocalData:
    @pytest.mark.real_data
    @pytest.mark.asyncio
    async def test_selected_data(self):
        assert True
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert findings == []


def test_checker_rejects_missing_and_conflicting_primary_tiers(
    checker, tmp_path: Path
) -> None:
    """Every test has one, and only one, primary tier."""
    missing_source = """
def test_missing_tier():
    assert True
"""
    conflicting_source = """
import pytest

@pytest.mark.unit
@pytest.mark.integration
def test_conflicting_tiers():
    assert True
"""

    _, missing = inspect_source(checker, tmp_path, missing_source)
    _, conflicting = inspect_source(checker, tmp_path, conflicting_source)

    assert [finding.code for finding in missing] == ['PRIMARY_TIER']
    assert [finding.code for finding in conflicting] == ['PRIMARY_TIER']
    assert 'unit, integration' in conflicting[0].message


def test_real_data_requires_the_integration_primary_tier(
    checker, tmp_path: Path
) -> None:
    """Caller-owned data cannot be classified as a unit or perf test."""
    source = """
import pytest

@pytest.mark.unit
@pytest.mark.real_data
def test_invalid_real_data_tier():
    assert True
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert [finding.code for finding in findings] == ['REAL_DATA_TIER']


def test_checker_rejects_noop_and_assertionless_tests(
    checker, tmp_path: Path
) -> None:
    """A marker and a function body alone do not prove behavior."""
    source = """
import pytest

@pytest.mark.unit
def test_noop():
    pass

@pytest.mark.unit
def test_assertionless():
    value = 1
    return value
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert [(finding.code, finding.line) for finding in findings] == [
        ('NOOP_TEST', 5),
        ('ASSERTION', 5),
        ('ASSERTION', 9),
    ]


def test_checker_rejects_assertion_hidden_in_uninvoked_helper(
    checker, tmp_path: Path
) -> None:
    """Only observations in the direct test body satisfy the checker."""
    source = """
import pytest

@pytest.mark.unit
def test_hollow():
    def hidden():
        assert False

    return None
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert [(finding.code, finding.line) for finding in findings] == [
        ('ASSERTION', 5),
    ]


def test_checker_accepts_exception_warning_and_mock_observation_contexts(
    checker, tmp_path: Path
) -> None:
    """Accepted assertion contexts cover common interaction-test styles."""
    source = """
import pytest

@pytest.mark.unit
def test_accepted_contexts(spy):
    with pytest.raises(ValueError):
        raise ValueError('expected')
    with pytest.warns(UserWarning):
        import warnings
        warnings.warn('expected', UserWarning)
    spy.assert_called_once()
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert findings == []


def test_checker_reports_print_and_name_mangled_access(
    checker, tmp_path: Path
) -> None:
    """Debug output and class-private seams are structural violations."""
    print_call = 'print' + "('debug')"
    private_name = '_Example' + '__private'
    source = f"""
import pytest

@pytest.mark.unit
def test_forbidden_seams():
    {print_call}
    value = object()
    value.{private_name}
    assert True
"""

    _, findings = inspect_source(checker, tmp_path, source)

    assert [finding.code for finding in findings] == [
        'RAW_PRINT',
        'NAME_MANGLED',
    ]


def test_checker_main_has_stable_file_line_diagnostics(
    checker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI diagnostics identify the same path and source line on each run."""
    path = tmp_path / 'test_diagnostics.py'
    print_call = 'print' + "('debug')"
    path.write_text(
        f'import pytest\n\n@pytest.mark.unit\ndef test_bad():\n'
        f'    {print_call}\n',
        encoding='utf-8',
    )

    result = checker.main([str(path)])
    output = capsys.readouterr().err

    assert result == 1
    assert f'{path}:5: [RAW_PRINT]' in output
    assert 'Resolution: classify each test' in output
