"""Require a reason for every construct that newly keeps a test from running.

The line-based integrity gate rejects added ``@pytest.mark.skip`` and
``@pytest.mark.xfail`` decorator lines. This module compares the inspected Git
snapshots of test modules and ``conftest.py`` files with their comparison base
and reports each construct that ``scripts.skip_constructs`` finds there and the
base lacks. Constructs are matched by identity, so one whose condition,
target, enclosing condition, or module value changed counts as new. A new
construct needs a ``skip-reason:`` on its own source lines that the base did
not already give a construct of the same kind in the same scope; a changed
construct therefore needs a new reason. A ``pytest.ini`` change to the
options that select or collect tests must add a ``# skip-reason:`` comment
line to that file.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from scripts.git_changes import read_git_base_file, read_git_file
from scripts.pytest_selection import (
    PYTEST_INI,
    default_deselected_markers,
    pytest_selection_errors,
)
from scripts.skip_constructs import MODULE_SCOPE, Signal, collect_signals

ALLOW_SKIP_RE = re.compile(
    r'(?:allow-skip|skip-reason):\s*(\S.*)', re.IGNORECASE
)
_ADDED_FILE_RE = re.compile(r'(?m)^\+\+\+ b/(.+)$')


def _parsed_base(
    source: str | None, deselected: frozenset[str]
) -> dict[str, list[Signal]]:
    """Parse the comparison base, treating an unusable base as empty."""
    if source is None:
        return {}
    try:
        return collect_signals(source, deselected)
    except (SyntaxError, ValueError):
        return {}


def _reasons(signal: Signal, lines: list[str]) -> set[str]:
    """Return the normalized reasons written on a signal's own lines."""
    reasons: set[str] = set()
    for number in range(signal.line, signal.end_line + 1):
        match = (
            ALLOW_SKIP_RE.search(lines[number - 1])
            if 0 < number <= len(lines)
            else None
        )
        if match:
            reasons.add(' '.join(match.group(1).split()).casefold())
    return reasons


def _signal_error(
    path: str, scope: str, signal: Signal, *, reused: bool
) -> str:
    """Render one actionable diagnostic for an unjustified signal."""
    target = 'the module' if scope == MODULE_SCOPE else f'`{scope}`'
    if signal.deselection:
        code = 'TEST_DESELECT'
        effect = 'leaves the default pytest selection'
    else:
        code = 'TEST_SKIP'
        effect = 'stops running or stops failing'
    location = f'{path}:{signal.line}: [{code}] {signal.label}'
    if reused:
        return (
            f'{location} added or changed in {target} keeps a reason the '
            'base already gave; write a "skip-reason:" for this change or '
            'revert it'
        )
    return (
        f'{location} added or changed in {target}, which {effect}; add '
        '"skip-reason: <why>" on that line or remove it'
    )


def added_signal_errors(
    path: str,
    base_source: str | None,
    source: str,
    deselected: frozenset[str],
) -> list[str]:
    """Report unjustified signals of ``source`` that the base lacks."""
    try:
        current = collect_signals(source, deselected)
    except (SyntaxError, ValueError) as error:
        line = getattr(error, 'lineno', None) or 1
        return [
            f'{path}:{line}: [TEST_PARSE] cannot inspect skip constructs '
            f'in the staged test module: {error}'
        ]
    previous = _parsed_base(base_source, deselected)
    lines = source.splitlines()
    base_lines = (base_source or '').splitlines()
    errors: list[str] = []
    for scope, signals in current.items():
        known = Counter(signal.identity for signal in previous.get(scope, ()))
        stated: dict[str, set[str]] = {}
        for signal in previous.get(scope, ()):
            reasons = _reasons(signal, base_lines)
            stated.setdefault(signal.label, set()).update(reasons)
        for signal in signals:
            if known[signal.identity] > 0:
                known[signal.identity] -= 1
                continue
            reasons = _reasons(signal, lines)
            if not reasons - stated.get(signal.label, set()):
                errors.append(
                    _signal_error(path, scope, signal, reused=bool(reasons))
                )
    return errors


def _inspected_python_files(
    paths: list[str], is_test_file: Callable[[str], bool]
) -> list[str]:
    """Return the changed test modules and ``conftest.py`` files."""
    return sorted(
        {
            path
            for path in paths
            if path.endswith('.py')
            and (is_test_file(path) or Path(path).name == 'conftest.py')
        }
    )


def skip_signal_errors(
    diff_text: str,
    is_test_file: Callable[[str], bool],
    *,
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    """Report unjustified skip and deselection constructs in a diff."""
    changed = _ADDED_FILE_RE.findall(diff_text)
    paths = _inspected_python_files(changed, is_test_file)
    selection_changed = PYTEST_INI in changed
    if not paths and not selection_changed:
        return []
    errors: list[str] = []
    current_ini = read_git_file(
        PYTEST_INI, revision_range=revision_range, repo_root=repo_root
    )
    if selection_changed:
        errors.extend(
            pytest_selection_errors(
                read_git_base_file(
                    PYTEST_INI,
                    revision_range=revision_range,
                    repo_root=repo_root,
                ),
                current_ini,
            )
        )
    try:
        deselected = default_deselected_markers(current_ini)
    except ValueError as error:
        if not selection_changed:
            errors.append(f'{PYTEST_INI}: [TEST_POLICY] {error}')
        deselected = frozenset()
    for path in paths:
        source = read_git_file(
            path,
            revision_range=revision_range,
            repo_root=repo_root,
            encoding_errors='replace',
        )
        if source is None:
            continue
        base_source = read_git_base_file(
            path,
            revision_range=revision_range,
            repo_root=repo_root,
            encoding_errors='replace',
        )
        errors.extend(
            added_signal_errors(path, base_source, source, deselected)
        )
    return errors
