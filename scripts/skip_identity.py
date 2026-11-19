"""Describe a skip construct by what it does rather than where it is.

An identity combines the construct's whole expression, the conditions that
enclose it, and the module- and class-level values those expressions read,
followed through other such values. Positions, formatting, and comments are
left out, so moving or reformatting a construct keeps its identity while
changing a condition, a target, or a value it reads does not.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence, Set

Guard = tuple[str, tuple[ast.expr, ...]]
Bindings = dict[str, list[ast.AST]]


def dump(node: ast.AST) -> str:
    """Render a node's structure without its position or formatting."""
    return ast.dump(node, annotate_fields=False, include_attributes=False)


class _BindingCollector(ast.NodeVisitor):
    """Map module- and class-level names to every node that binds them.

    Function bodies are not entered: their names are local to each call.
    """

    def __init__(self) -> None:
        self.bindings: Bindings = {}

    def _bind(self, target: ast.AST, value: ast.AST) -> None:
        """Bind every name a target assigns to the assigned value."""
        for name in ast.walk(target):
            if isinstance(name, ast.Name):
                self.bindings.setdefault(name.id, []).append(value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Bind a function's name to its whole definition."""
        self.bindings.setdefault(node.name, []).append(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Bind a coroutine function's name to its whole definition."""
        self.bindings.setdefault(node.name, []).append(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Bind a class's name and the names assigned in its body."""
        self.bindings.setdefault(node.name, []).append(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Bind each assigned name to the value."""
        for target in node.targets:
            self._bind(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Bind an annotated name that receives a value."""
        if node.value is not None:
            self._bind(node.target, node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Bind an augmented name to the value it adds."""
        self._bind(node.target, node.value)


def module_bindings(tree: ast.Module) -> Bindings:
    """Return the module- and class-level bindings of a parsed module."""
    collector = _BindingCollector()
    collector.visit(tree)
    return collector.bindings


def _read_values(
    roots: Sequence[ast.AST],
    bindings: Bindings,
    aliases: Mapping[str, str],
    excluded: Set[str],
) -> list[str]:
    """Render the imports and module values that expressions read."""
    rendered: set[str] = set()
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        names = {
            child.id
            for child in ast.walk(pending.pop())
            if isinstance(child, ast.Name)
        }
        for name in sorted(names - seen - excluded):
            seen.add(name)
            if name in aliases:
                rendered.add(f'{name} = import {aliases[name]}')
            for value in bindings.get(name, ()):
                rendered.add(f'{name} = {dump(value)}')
                pending.append(value)
    return sorted(rendered)


def construct_identity(
    label: str,
    node: ast.AST,
    guards: Sequence[Guard],
    *,
    bindings: Bindings,
    aliases: Mapping[str, str],
    excluded: Set[str],
) -> str:
    """Describe what a construct does, independent of its position.

    Names in ``excluded``, such as marker aliases whose definitions are
    signals of their own, are not followed.
    """
    conditions = [
        (kind, [dump(test) for test in tests]) for kind, tests in guards
    ]
    tests = [test for _, enclosing in guards for test in enclosing]
    reads = _read_values([node, *tests], bindings, aliases, excluded)
    return repr((label, dump(node), conditions, reads))
