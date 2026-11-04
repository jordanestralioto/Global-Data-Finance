"""Run explicit Ruff base, documentation, and security profiles."""

from __future__ import annotations

import argparse
import shlex
import sys
import tomllib
from pathlib import Path
from typing import Final, NamedTuple

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.process_runner import ProcessRunnerError, run_process

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUFF_PATHS: Final[tuple[str, ...]] = ('src', 'tests', 'scripts', 'examples')
BASE_RULES: Final[tuple[str, ...]] = (
    'E',
    'W',
    'F',
    'I',
    'UP',
    'B',
    'C4',
    'SIM',
    'RUF',
    'PTH',
    'ARG',
    'LOG',
    'C901',
    'BLE001',
    'TRY203',
    'TRY400',
    'TRY401',
)
EXPECTED_PER_FILE_IGNORES: Final[dict[str, tuple[str, ...]]] = {
    'scripts/process_runner.py': ('S603',),
}
EXPECTED_RUFF_KEYS: Final[frozenset[str]] = frozenset(
    {'line-length', 'lint', 'format'}
)
EXPECTED_LINT_KEYS: Final[frozenset[str]] = frozenset(
    {'select', 'pydocstyle', 'isort', 'mccabe', 'per-file-ignores'}
)
EXPECTED_PYDOCSTYLE_KEYS: Final[frozenset[str]] = frozenset({'convention'})
EXPECTED_ISORT_KEYS: Final[frozenset[str]] = frozenset({'known-first-party'})
EXPECTED_MCCABE_KEYS: Final[frozenset[str]] = frozenset({'max-complexity'})
EXPECTED_FORMAT_KEYS: Final[frozenset[str]] = frozenset(
    {
        'quote-style',
        'indent-style',
        'skip-magic-trailing-comma',
        'line-ending',
    }
)
EXPECTED_FORMAT_VALUES: Final[dict[str, object]] = {
    'quote-style': 'single',
    'indent-style': 'space',
    'skip-magic-trailing-comma': False,
    'line-ending': 'auto',
}
PROFILE_NAMES: Final[tuple[str, ...]] = ('all', 'base', 'docs', 'security')


class RuffPolicyError(RuntimeError):
    """Raised when the Ruff policy cannot be read or validated."""


class _RuffPolicyTables(NamedTuple):
    """Closed set of Ruff tables required by the repository policy."""

    ruff: dict[str, object]
    lint: dict[str, object]
    pydocstyle: dict[str, object]
    isort: dict[str, object]
    mccabe: dict[str, object]
    format_options: dict[str, object]


def _as_mapping(value: object, label: str) -> dict[str, object]:
    """Return a TOML table or raise a contextual policy error."""
    if not isinstance(value, dict):
        raise RuffPolicyError(f'{label} must be a TOML table')
    return value


def _unexpected_keys(
    table: dict[str, object],
    expected: frozenset[str],
    label: str,
) -> list[str]:
    """Return diagnostics for keys outside one closed Ruff table."""
    return [
        f'{label}.{key} is not allowed; the Ruff policy shape is closed'
        for key in sorted(set(table) - expected)
    ]


def _is_string_list(value: object, expected: tuple[str, ...]) -> bool:
    """Return whether a TOML value is exactly one expected string list."""
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and tuple(value) == expected
    )


def _read_pyproject(pyproject_path: Path) -> dict[str, object]:
    """Read the repository TOML configuration without executing tooling."""
    try:
        with pyproject_path.open('rb') as file_handle:
            return tomllib.load(file_handle)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise RuffPolicyError(
            f'Unable to read Ruff policy from {pyproject_path}: {err}'
        ) from err


def _require_policy_values(tables: _RuffPolicyTables) -> None:
    """Require every scalar value consumed by policy validation."""
    required_keys = (
        (tables.ruff, 'line-length'),
        (tables.lint, 'select'),
        (tables.lint, 'per-file-ignores'),
        (tables.pydocstyle, 'convention'),
        (tables.isort, 'known-first-party'),
        (tables.mccabe, 'max-complexity'),
    )
    for table, key in required_keys:
        if key not in table:
            raise RuffPolicyError(f'Missing Ruff policy key: {key}')


def _load_policy_tables(pyproject_path: Path) -> _RuffPolicyTables:
    """Load every required Ruff table and key from the project manifest."""
    data = _read_pyproject(pyproject_path)
    try:
        tool = _as_mapping(data['tool'], '[tool]')
        ruff = _as_mapping(tool['ruff'], '[tool.ruff]')
        lint = _as_mapping(ruff['lint'], '[tool.ruff.lint]')
        pydocstyle = _as_mapping(
            lint['pydocstyle'], '[tool.ruff.lint.pydocstyle]'
        )
        isort = _as_mapping(lint['isort'], '[tool.ruff.lint.isort]')
        mccabe = _as_mapping(lint['mccabe'], '[tool.ruff.lint.mccabe]')
        format_options = _as_mapping(ruff['format'], '[tool.ruff.format]')
    except KeyError as err:
        raise RuffPolicyError(
            f'Missing Ruff policy key: {err.args[0]}'
        ) from err
    tables = _RuffPolicyTables(
        ruff=ruff,
        lint=lint,
        pydocstyle=pydocstyle,
        isort=isort,
        mccabe=mccabe,
        format_options=format_options,
    )
    _require_policy_values(tables)
    return tables


def _validate_policy_shape(tables: _RuffPolicyTables) -> list[str]:
    """Return diagnostics for keys outside the closed Ruff policy shape."""
    errors: list[str] = []
    errors.extend(
        _unexpected_keys(tables.ruff, EXPECTED_RUFF_KEYS, '[tool.ruff]')
    )
    errors.extend(
        _unexpected_keys(tables.lint, EXPECTED_LINT_KEYS, '[tool.ruff.lint]')
    )
    errors.extend(
        _unexpected_keys(
            tables.pydocstyle,
            EXPECTED_PYDOCSTYLE_KEYS,
            '[tool.ruff.lint.pydocstyle]',
        )
    )
    errors.extend(
        _unexpected_keys(
            tables.isort,
            EXPECTED_ISORT_KEYS,
            '[tool.ruff.lint.isort]',
        )
    )
    errors.extend(
        _unexpected_keys(
            tables.mccabe,
            EXPECTED_MCCABE_KEYS,
            '[tool.ruff.lint.mccabe]',
        )
    )
    errors.extend(
        _unexpected_keys(
            tables.format_options,
            EXPECTED_FORMAT_KEYS,
            '[tool.ruff.format]',
        )
    )
    return errors


def _validate_per_file_ignores(value: object) -> list[str]:
    """Validate the sole approved file-scoped Ruff exception."""
    if not isinstance(value, dict):
        return ['[tool.ruff.lint.per-file-ignores] must be a TOML table']

    normalized = {
        str(path): tuple(rules) if isinstance(rules, list) else None
        for path, rules in value.items()
    }
    if normalized == EXPECTED_PER_FILE_IGNORES:
        return []
    return [
        '[tool.ruff.lint.per-file-ignores] must contain only '
        '`scripts/process_runner.py = ["S603"]`'
    ]


def _validate_policy_values(tables: _RuffPolicyTables) -> list[str]:
    """Return diagnostics for noncanonical values in approved Ruff keys."""
    errors: list[str] = []
    configured_line_length = tables.ruff['line-length']

    if type(configured_line_length) is not int or configured_line_length != 79:
        errors.append('[tool.ruff].line-length must be exactly 79')

    if not _is_string_list(tables.lint['select'], BASE_RULES):
        errors.append(
            '[tool.ruff.lint].select must contain exactly the explicit base '
            f'rules: {list(BASE_RULES)}'
        )
    errors.extend(_validate_per_file_ignores(tables.lint['per-file-ignores']))
    if tables.pydocstyle['convention'] != 'google':
        errors.append(
            '[tool.ruff.lint.pydocstyle].convention must remain "google"'
        )
    if not _is_string_list(
        tables.isort['known-first-party'], ('globaldatafinance',)
    ):
        errors.append(
            '[tool.ruff.lint.isort].known-first-party must contain exactly '
            '["globaldatafinance"]'
        )
    configured_complexity = tables.mccabe['max-complexity']
    if type(configured_complexity) is not int or configured_complexity != 10:
        errors.append(
            '[tool.ruff.lint.mccabe].max-complexity must be exactly 10'
        )

    for key, expected in EXPECTED_FORMAT_VALUES.items():
        configured_value = tables.format_options.get(key)
        if (
            type(configured_value) is not type(expected)
            or configured_value != expected
        ):
            errors.append(f'[tool.ruff.format].{key} must remain {expected!r}')
    return errors


def validate_ruff_policy(pyproject_path: Path) -> list[str]:
    """Return violations of the repository's explicit Ruff policy."""
    tables = _load_policy_tables(pyproject_path)
    return _validate_policy_shape(tables) + _validate_policy_values(tables)


def build_profile_commands(profile: str) -> tuple[tuple[str, ...], ...]:
    """Build the concrete, path-scoped Ruff commands for one profile."""
    if profile not in PROFILE_NAMES:
        raise RuffPolicyError(
            f'Unknown Ruff profile {profile!r}; choose from {PROFILE_NAMES}'
        )

    base_command = (
        'uv',
        'run',
        '--locked',
        '--no-sync',
        'ruff',
        'check',
        '--select',
        ','.join(BASE_RULES),
        *RUFF_PATHS,
    )
    docs_command = (
        'uv',
        'run',
        '--locked',
        '--no-sync',
        'ruff',
        'check',
        '--select',
        'D',
        '--exclude',
        '**/__init__.py',
        'src',
        'scripts',
        'examples',
    )
    security_commands = (
        (
            'uv',
            'run',
            '--locked',
            '--no-sync',
            'ruff',
            'check',
            '--select',
            'S',
            'src',
            'scripts',
            'examples',
        ),
        (
            'uv',
            'run',
            '--locked',
            '--no-sync',
            'ruff',
            'check',
            '--select',
            'S',
            '--ignore',
            'S101',
            'tests',
        ),
    )
    if profile == 'base':
        return (base_command,)
    if profile == 'docs':
        return (docs_command,)
    if profile == 'security':
        return security_commands
    return (base_command, docs_command, *security_commands)


def _emit_result(
    command: tuple[str, ...], returncode: int, stdout: str, stderr: str
) -> None:
    """Forward a profile result while retaining an actionable command label."""
    print(f'RUN [RUFF_POLICY]: {shlex.join(command)}')
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    if returncode:
        print(
            f'FAIL [RUFF_POLICY]: command exited with status {returncode}',
            file=sys.stderr,
        )


def run_profile(profile: str, repo_root: Path) -> int:
    """Run all commands in a profile and return its aggregate status."""
    failed = False
    for command in build_profile_commands(profile):
        try:
            result = run_process(command, cwd=repo_root, check=False)
        except ProcessRunnerError as err:
            print(f'ERROR [RUFF_POLICY]: {err}', file=sys.stderr)
            return 2
        _emit_result(
            command,
            result.returncode,
            result.stdout or '',
            result.stderr or '',
        )
        failed |= result.returncode != 0
    return 1 if failed else 0


def main() -> int:
    """Validate the configuration and run the selected Ruff profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILE_NAMES, default='all')
    args = parser.parse_args()

    try:
        policy_errors = validate_ruff_policy(
            REPOSITORY_ROOT / 'pyproject.toml'
        )
    except RuffPolicyError as err:
        print(f'ERROR [RUFF_POLICY]: {err}', file=sys.stderr)
        return 2
    if policy_errors:
        print(
            'FAIL [RUFF_POLICY]: Invalid Ruff policy configuration:',
            file=sys.stderr,
        )
        for error in policy_errors:
            print(f'  • {error}', file=sys.stderr)
        return 1

    return run_profile(args.profile, REPOSITORY_ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
