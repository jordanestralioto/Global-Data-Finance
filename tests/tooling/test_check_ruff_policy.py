"""Tests for the explicit Ruff profile and configuration policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / 'scripts'
CHECKER_PATH = SCRIPTS_ROOT / 'check-ruff-policy.py'


pytestmark = pytest.mark.unit


@pytest.fixture
def checker(monkeypatch: pytest.MonkeyPatch):
    """Load the hyphenated Ruff policy CLI as a test module."""
    monkeypatch.syspath_prepend(str(SCRIPTS_ROOT))
    spec = importlib.util.spec_from_file_location(
        'check_ruff_policy', CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError('Unable to load check-ruff-policy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_policy(tmp_path: Path, *, ignore: str = '') -> Path:
    """Write the canonical complete Ruff policy fixture."""
    ignore_section = f'ignore = [{ignore}]\n' if ignore else ''
    content = f"""[tool.ruff]
line-length = 79

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4", "SIM", "RUF", "PTH",
"ARG", "LOG", "C901", "BLE001", "TRY203", "TRY400", "TRY401"]
{ignore_section}
[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.isort]
known-first-party = ["globaldatafinance"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
"scripts/process_runner.py" = ["S603"]

[tool.ruff.format]
quote-style = "single"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
"""
    path = tmp_path / 'pyproject.toml'
    path.write_text(content, encoding='utf-8')
    return path


def test_real_pyproject_has_only_the_adapter_exception(checker) -> None:
    """The repository policy must contain no broad Ruff suppression."""
    assert (
        checker.validate_ruff_policy(REPOSITORY_ROOT / 'pyproject.toml') == []
    )


def test_policy_rejects_a_global_ignore(checker, tmp_path: Path) -> None:
    """A global ignore must fail even when the exception table is narrow."""
    policy = write_policy(tmp_path, ignore='"E501"')

    errors = checker.validate_ruff_policy(policy)

    assert any(
        '[tool.ruff.lint].ignore is not allowed' in error for error in errors
    )


def test_policy_rejects_extended_scopes_and_exceptions(
    checker, tmp_path: Path
) -> None:
    """Global rule extensions must not bypass the explicit profile scopes."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace(
        '[tool.ruff.lint]\n',
        '[tool.ruff.lint]\nextend-select = ["D"]\n'
        'extend-per-file-ignores = {"tests/*.py" = ["S101"]}\n',
    )
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    errors = checker.validate_ruff_policy(path)

    assert any(
        '[tool.ruff.lint].extend-select is not allowed' in error
        for error in errors
    )
    assert any(
        '[tool.ruff.lint].extend-per-file-ignores is not allowed' in error
        for error in errors
    )


def test_policy_rejects_any_per_file_exception_other_than_the_adapter(
    checker,
    tmp_path: Path,
) -> None:
    """Test and script-wide exceptions must not return to the policy."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace(
        '"scripts/process_runner.py" = ["S603"]',
        '"tests/**/*.py" = ["S101"]',
    )
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    errors = checker.validate_ruff_policy(path)

    assert any('per-file-ignores' in error for error in errors)


@pytest.mark.parametrize(
    ('section', 'extra_key'),
    [
        ('[tool.ruff]', 'exclude = ["src"]'),
        ('[tool.ruff.lint]', 'ignore = ["E501"]'),
        (
            '[tool.ruff.lint.pydocstyle]',
            'extend-convention = "numpy"',
        ),
        ('[tool.ruff.lint.isort]', 'force-single-line = true'),
        ('[tool.ruff.lint.mccabe]', 'extra-setting = true'),
        ('[tool.ruff.format]', 'docstring-code-format = true'),
    ],
    ids=['ruff', 'lint', 'pydocstyle', 'isort', 'mccabe', 'format'],
)
def test_policy_rejects_unexpected_keys_in_every_ruff_table(
    checker,
    tmp_path: Path,
    section: str,
    extra_key: str,
) -> None:
    """Every nested Ruff table must reject unapproved configuration keys."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace(section, f'{section}\n{extra_key}', 1)
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    errors = checker.validate_ruff_policy(path)

    assert any(
        section in error and 'is not allowed' in error for error in errors
    )


@pytest.mark.parametrize(
    ('configured_value', 'expected_error'),
    [
        ('true', True),
        ('9', True),
        ('11', True),
        ('"10"', True),
        ('10', False),
    ],
    ids=['boolean', 'lower', 'higher', 'string', 'exact'],
)
def test_policy_requires_exact_mccabe_complexity(
    checker,
    tmp_path: Path,
    configured_value: str,
    expected_error: bool,
) -> None:
    """McCabe complexity must be the integer ten, not a coercible value."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace(
        'max-complexity = 10', f'max-complexity = {configured_value}'
    )
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    errors = checker.validate_ruff_policy(path)

    assert any('max-complexity' in error for error in errors) is expected_error


def test_policy_rejects_missing_mccabe_complexity(
    checker, tmp_path: Path
) -> None:
    """A missing complexity limit must be reported as an incomplete policy."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace('max-complexity = 10\n', '')
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    with pytest.raises(checker.RuffPolicyError, match='max-complexity'):
        checker.validate_ruff_policy(path)


@pytest.mark.parametrize(
    'focused_rule',
    ['C901', 'BLE001', 'TRY203', 'TRY400', 'TRY401'],
)
def test_policy_rejects_removing_a_focused_rule(
    checker, tmp_path: Path, focused_rule: str
) -> None:
    """Every conditional and exception rule must remain in the base gate."""
    policy = write_policy(tmp_path).read_text(encoding='utf-8')
    policy = policy.replace(f', "{focused_rule}"', '')
    path = tmp_path / 'pyproject.toml'
    path.write_text(policy, encoding='utf-8')

    errors = checker.validate_ruff_policy(path)

    assert any('[tool.ruff.lint].select' in error for error in errors)


def test_profile_commands_have_exact_scopes_and_exceptions(checker) -> None:
    """Each profile must expose its paths and the two deliberate exclusions."""
    base = checker.build_profile_commands('base')[0]
    docs = checker.build_profile_commands('docs')[0]
    security = checker.build_profile_commands('security')

    assert base[base.index('--select') + 1] == ','.join(checker.BASE_RULES)
    assert base[-4:] == ('src', 'tests', 'scripts', 'examples')
    assert docs[docs.index('--select') + 1] == 'D'
    assert docs[docs.index('--exclude') + 1] == '**/__init__.py'
    assert docs[-3:] == ('src', 'scripts', 'examples')
    assert security[0][-3:] == ('src', 'scripts', 'examples')
    assert security[1][security[1].index('--ignore') + 1] == 'S101'
    assert security[1][-1] == 'tests'


def test_all_profile_runs_all_three_profiles(
    checker, monkeypatch, tmp_path: Path
) -> None:
    """The aggregate profile must execute every configured Ruff scope."""
    commands: list[tuple[str, ...]] = []

    def fake_run(command, *, cwd, check):
        assert cwd == tmp_path
        assert check is False
        commands.append(command)
        return type(
            'Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''}
        )()

    monkeypatch.setattr(checker, 'run_process', fake_run)

    assert checker.run_profile('all', tmp_path) == 0
    assert commands == list(checker.build_profile_commands('all'))
