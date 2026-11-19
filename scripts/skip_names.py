"""Classify the names that denote skip, xfail, and deselection constructs.

Names are resolved through the module's imports, so ``from unittest import
skip`` and ``import pytest as pt`` denote the same constructs as their
qualified spellings.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import NamedTuple

SKIP_MARKERS = frozenset({'skip', 'skipif', 'xfail'})
PYTEST_OUTCOMES = frozenset({'skip', 'xfail', 'importorskip'})
OUTCOME_ERRORS: Mapping[str, str] = {'Skipped': 'skip', 'XFailed': 'xfail'}
UNITTEST_SKIPS = frozenset(
    {'skip', 'skipIf', 'skipUnless', 'expectedFailure', 'SkipTest'}
)
_STAR_EXPORTS: Mapping[str, frozenset[str]] = {
    'pytest': frozenset({'mark', *PYTEST_OUTCOMES}),
    '_pytest.outcomes': PYTEST_OUTCOMES,
    'unittest': UNITTEST_SKIPS,
    'unittest.case': UNITTEST_SKIPS,
}


class Classification(NamedTuple):
    """How a reference stops a test, if it does.

    ``raised_only`` marks exception classes: raising one skips the test,
    while catching or expecting it, as ``pytest.raises`` does, does not.
    """

    label: str
    deselection: bool
    raised_only: bool = False


def import_aliases(tree: ast.AST) -> dict[str, str]:
    """Map every name a module binds by import to its qualified name."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    top = alias.name.partition('.')[0]
                    aliases[top] = top
        elif (
            isinstance(node, ast.ImportFrom) and node.module and not node.level
        ):
            for alias in node.names:
                if alias.name == '*':
                    for name in _STAR_EXPORTS.get(node.module, ()):
                        aliases[name] = f'{node.module}.{name}'
                else:
                    bound = alias.asname or alias.name
                    aliases[bound] = f'{node.module}.{alias.name}'
    return aliases


def qualified_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    """Return the dotted name an expression denotes through imports."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        owner = qualified_name(node.value, aliases)
        return None if owner is None else f'{owner}.{node.attr}'
    return None


def classify(
    qualified: str, deselected: frozenset[str]
) -> Classification | None:
    """Return how a skip-capable qualified name affects a test."""
    parts = qualified.split('.')
    if parts[0] in {'pytest', '_pytest'} and parts[1:2] == ['mark']:
        name = parts[2] if len(parts) > 2 else ''
        if name in deselected:
            return Classification(f'pytest.mark.{name}', True)
        if name in SKIP_MARKERS:
            return Classification(f'pytest.mark.{name}', False)
        return None
    outcome_owners = (['pytest'], ['_pytest', 'outcomes'])
    if parts[-1] in PYTEST_OUTCOMES and parts[:-1] in outcome_owners:
        return Classification(f'pytest.{parts[-1]}', False)
    if (
        parts[-1] == 'Exception'
        and len(parts) > 1
        and parts[-2] in PYTEST_OUTCOMES
        and parts[:-2] in outcome_owners
    ):
        return Classification(f'pytest.{parts[-2]}', False, True)
    if parts[:-1] == ['_pytest', 'outcomes'] and parts[-1] in OUTCOME_ERRORS:
        label = f'pytest.{OUTCOME_ERRORS[parts[-1]]}'
        return Classification(label, False, True)
    if parts[-1] in UNITTEST_SKIPS and parts[:-1] in (
        ['unittest'],
        ['unittest', 'case'],
    ):
        raised_only = parts[-1] == 'SkipTest'
        return Classification(f'unittest.{parts[-1]}', False, raised_only)
    return None
