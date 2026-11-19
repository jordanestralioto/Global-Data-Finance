"""Read pytest markers from Python syntax trees without importing tests."""

from __future__ import annotations

import ast


def marker_name(node: ast.AST) -> str | None:
    """Return the name of a ``pytest.mark.<name>`` marker or marker call."""
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute):
        return None
    parent = node.value
    if not isinstance(parent, ast.Attribute) or parent.attr != 'mark':
        return None
    if not isinstance(parent.value, ast.Name) or parent.value.id != 'pytest':
        return None
    return node.attr


def expression_markers(node: ast.AST) -> list[tuple[str, ast.AST]]:
    """Return the markers of a ``pytestmark`` value with their nodes."""
    elements = (
        node.elts
        if isinstance(node, (ast.List, ast.Set, ast.Tuple))
        else [node]
    )
    return [
        (name, element)
        for element in elements
        if (name := marker_name(element)) is not None
    ]


def pytestmark_value(statement: ast.stmt) -> ast.expr | None:
    """Return the value one statement assigns to ``pytestmark``."""
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign):
        targets = [statement.target]
    else:
        return None
    if any(
        isinstance(target, ast.Name) and target.id == 'pytestmark'
        for target in targets
    ):
        return statement.value
    return None
