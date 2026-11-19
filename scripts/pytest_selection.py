"""Read the pytest.ini options that decide which tests run by default."""

from __future__ import annotations

import configparser
import re
import shlex
from collections import Counter

PYTEST_INI = 'pytest.ini'
SELECTION_KEYS = (
    'testpaths',
    'python_files',
    'python_classes',
    'python_functions',
    'norecursedirs',
    'xfail_strict',
    'empty_parameter_set_mark',
)
SELECTION_OPTIONS = frozenset(
    {
        '-m',
        '-k',
        '-p',
        '--deselect',
        '--ignore',
        '--ignore-glob',
        '--co',
        '--collect-only',
        '--lf',
        '--last-failed',
        '--sw',
        '--stepwise',
        '--stepwise-skip',
        '--noconftest',
        '--confcutdir',
        '--continue-on-collection-errors',
    }
)
VALUED_SELECTION_OPTIONS = frozenset(
    {'-m', '-k', '-p', '--deselect', '--ignore', '--ignore-glob'}
)
_NEGATED_MARKER_RE = re.compile(r'\bnot\s+([A-Za-z_]\w*)')
_INI_REASON_RE = re.compile(r'(?m)^\s*[#;].*skip-reason:\s*\S', re.IGNORECASE)


def _pytest_options(
    pytest_ini: str | None,
) -> configparser.SectionProxy | None:
    """Parse the ``[pytest]`` section of a ``pytest.ini`` snapshot.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    if not pytest_ini:
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(pytest_ini)
    except configparser.Error as error:
        raise ValueError(f'invalid {PYTEST_INI}: {error}') from error
    return parser['pytest'] if parser.has_section('pytest') else None


def _addopts(options: configparser.SectionProxy | None) -> list[str]:
    """Split ``addopts`` into shell-style tokens.

    Raises:
        ValueError: If the option string cannot be tokenized.
    """
    if options is None:
        return []
    try:
        return shlex.split(options.get('addopts', fallback=''))
    except ValueError as error:
        raise ValueError(f'invalid {PYTEST_INI} addopts: {error}') from error


def default_deselected_markers(pytest_ini: str | None) -> frozenset[str]:
    """Return the markers that the default ``-m`` expression excludes.

    Raises:
        ValueError: If ``pytest.ini`` or its ``addopts`` cannot be parsed.
    """
    options = _addopts(_pytest_options(pytest_ini))
    expression = ''
    for index, option in enumerate(options):
        if option == '-m' and index + 1 < len(options):
            expression = options[index + 1]
        elif option.startswith('-m') and len(option) > len('-m'):
            expression = option.removeprefix('-m').lstrip('=')
    return frozenset(_NEGATED_MARKER_RE.findall(expression))


def selection_options(pytest_ini: str | None) -> Counter[str]:
    """Return the ``addopts`` options that narrow collection or selection.

    Raises:
        ValueError: If ``pytest.ini`` or its ``addopts`` cannot be parsed.
    """
    tokens = _addopts(_pytest_options(pytest_ini))
    selected: Counter[str] = Counter()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        name, separator, inline_value = token.partition('=')
        if name not in SELECTION_OPTIONS and not (
            name[:2] in {'-m', '-k', '-p'} and len(name) > 2
        ):
            index += 1
            continue
        if name in VALUED_SELECTION_OPTIONS and not separator:
            value = tokens[index + 1] if index + 1 < len(tokens) else ''
            selected[f'{name} {value}'] += 1
            index += 2
            continue
        selected[f'{name}{separator}{inline_value}'] += 1
        index += 1
    return selected


def _selection_values(pytest_ini: str | None) -> dict[str, str]:
    """Return the normalized collection keys of a ``pytest.ini`` snapshot."""
    options = _pytest_options(pytest_ini)
    if options is None:
        return {}
    return {
        key: ' '.join(options[key].split())
        for key in SELECTION_KEYS
        if key in options
    }


def pytest_selection_errors(
    base_ini: str | None, current_ini: str | None
) -> list[str]:
    """Report unjustified ``pytest.ini`` changes to the default selection."""
    try:
        current_options = selection_options(current_ini)
        current_values = _selection_values(current_ini)
    except ValueError as error:
        return [f'{PYTEST_INI}: [TEST_POLICY] {error}']
    try:
        base_options = selection_options(base_ini)
        base_values = _selection_values(base_ini)
    except ValueError:
        base_options, base_values = Counter(), {}
    changes = sorted((current_options - base_options).elements())
    changes.extend(
        f'{key} = {current_values.get(key, "<unset>")}'
        for key in SELECTION_KEYS
        if current_values.get(key) != base_values.get(key)
    )
    reasons = len(_INI_REASON_RE.findall(current_ini or ''))
    if not changes or reasons > len(_INI_REASON_RE.findall(base_ini or '')):
        return []
    return [
        f'{PYTEST_INI}: [TEST_DESELECT] {change} changes which tests run '
        'by default; add a "# skip-reason: <why>" comment line or revert it'
        for change in changes
    ]
