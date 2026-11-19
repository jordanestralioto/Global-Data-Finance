"""Find references to constructs that stop Python tests from running.

The collector parses one module and reports every reference to a construct
that skips a test, expects it to fail, or removes it from the default
selection, wherever the expression appears: decorators, ``pytestmark``,
``pytest.param(marks=...)``, ``applymarker``, and aliases. It covers pytest
skip markers and the caller's deselected markers, the ``skip``/``xfail``/
``importorskip`` outcomes and their exceptions, unittest skip decorators and
``SkipTest``, ``skipTest`` calls, ``collect_ignore`` entries, and collection
hooks. Import bindings (``from unittest import skip``, ``import pytest as pt``)
and module-level aliases (``SLOW = pytest.mark.slow``) are resolved.

Each signal carries the identity ``scripts.skip_identity`` builds from its
expression, the ``if``, ``while``, conditional-expression, boolean, and
``except`` conditions that enclose it, and the module values they read.

The analysis is syntactic and per module: local variables, markers or
helpers imported from other modules, ``getattr`` lookups, and plugins outside
the module are not followed.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from scripts.skip_identity import (
    Bindings,
    Guard,
    construct_identity,
    module_bindings,
)
from scripts.skip_names import (
    Classification,
    classify,
    import_aliases,
    qualified_name,
)

LINE_GATE_DECORATOR_RE = re.compile(r'@pytest\.mark\.(?:skip|xfail)\b')
COLLECTION_LISTS = frozenset({'collect_ignore', 'collect_ignore_glob'})
COLLECTION_HOOKS = frozenset(
    {'pytest_ignore_collect', 'pytest_collection_modifyitems'}
)
MODULE_SCOPE = '<module>'
_LIST_MUTATIONS = frozenset({'append', 'extend', 'insert'})

Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass(frozen=True)
class Signal:
    """One construct that keeps a test out of the default run."""

    label: str
    line: int
    end_line: int
    deselection: bool
    identity: str


class _SignalCollector(ast.NodeVisitor):
    """Collect signals per module, class, and function scope."""

    def __init__(self, lines: list[str], deselected: frozenset[str]) -> None:
        self.scopes: dict[str, list[Signal]] = {MODULE_SCOPE: []}
        self._lines = lines
        self._deselected = deselected
        self._aliases: dict[str, str] = {}
        self._local: dict[str, Classification] = {}
        self._bindings: Bindings = {}
        self._guards: list[Guard] = []
        self._stack: list[str] = []

    def collect(self, tree: ast.Module) -> dict[str, list[Signal]]:
        """Visit one module after binding its imports and marker aliases."""
        self._aliases = import_aliases(tree)
        self._bind_marker_aliases(tree.body)
        self._bindings = module_bindings(tree)
        self.visit(tree)
        return self.scopes

    def _bind_marker_aliases(self, statements: list[ast.stmt]) -> None:
        """Bind module and class names assigned a skip-capable expression."""
        for statement in statements:
            if isinstance(statement, ast.ClassDef):
                self._bind_marker_aliases(statement.body)
                continue
            if not isinstance(statement, ast.Assign):
                continue
            value = statement.value
            target = value.func if isinstance(value, ast.Call) else value
            classification = self._classification(target)
            if classification is None:
                continue
            for name in statement.targets:
                if isinstance(name, ast.Name) and name.id != 'pytestmark':
                    self._local[name.id] = classification

    def _classification(self, node: ast.AST) -> Classification | None:
        """Classify one expression that may denote a skip construct."""
        if isinstance(node, ast.Attribute) and node.attr == 'skipTest':
            return Classification('TestCase.skipTest', False)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == 'pytest_deselected'
        ):
            return Classification('hook pytest_deselected', True)
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                return None
            if node.id in self._local:
                return self._local[node.id]
        qualified = qualified_name(node, self._aliases)
        return (
            None
            if qualified is None
            else classify(qualified, self._deselected)
        )

    def _identity(self, label: str, node: ast.AST) -> str:
        """Describe what a construct does, independent of its position.

        Marker aliases are not followed: their definitions are signals of
        their own, so a changed alias is reported once, where it is defined.
        """
        return construct_identity(
            label,
            node,
            self._guards,
            bindings=self._bindings,
            aliases=self._aliases,
            excluded=self._local.keys(),
        )

    def _emit(self, label: str, node: ast.AST, *, deselection: bool) -> None:
        """Record a signal at the source lines of one node."""
        line = getattr(node, 'lineno', 1)
        end_line = getattr(node, 'end_lineno', None) or line
        identity = self._identity(label, node)
        self._record(Signal(label, line, end_line, deselection, identity))

    def _emit_classified(
        self, classification: Classification, node: ast.AST
    ) -> None:
        """Record a classified reference at the source lines of a node."""
        self._emit(
            classification.label,
            node,
            deselection=classification.deselection,
        )

    def _record(self, signal: Signal) -> None:
        """Attribute a signal to the innermost enclosing scope."""
        scope = '::'.join(self._stack) or MODULE_SCOPE
        self.scopes.setdefault(scope, []).append(signal)

    def _line_gated(self, decorator: ast.AST) -> bool:
        """Return whether the line-based gate already owns a decorator."""
        target = (
            decorator.func if isinstance(decorator, ast.Call) else decorator
        )
        name = qualified_name(target, {'pytest': 'pytest'})
        number = getattr(decorator, 'lineno', 0)
        line = (
            self._lines[number - 1] if 0 < number <= len(self._lines) else ''
        )
        return name in {'pytest.mark.skip', 'pytest.mark.xfail'} and bool(
            LINE_GATE_DECORATOR_RE.search(line)
        )

    def _definition(self, node: Definition) -> None:
        """Visit a definition inside its own scope."""
        self._stack.append(node.name)
        self.scopes.setdefault('::'.join(self._stack), [])
        if (
            not isinstance(node, ast.ClassDef)
            and node.name in COLLECTION_HOOKS
        ):
            label = f'hook {node.name}'
            signature_end = max(node.lineno, node.body[0].lineno - 1)
            self._record(
                Signal(
                    label,
                    node.lineno,
                    signature_end,
                    True,
                    self._identity(label, node),
                )
            )
        for field, value in ast.iter_fields(node):
            items = value if isinstance(value, list) else [value]
            for item in items:
                if not isinstance(item, ast.AST):
                    continue
                if field == 'decorator_list' and self._line_gated(item):
                    continue
                self.visit(item)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function in its own scope."""
        self._definition(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit a coroutine function in its own scope."""
        self._definition(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class in its own scope."""
        self._definition(node)

    def _guarded(
        self, kind: str, tests: tuple[ast.expr, ...], nodes: Sequence[ast.AST]
    ) -> None:
        """Visit nodes that run only when the given conditions allow it."""
        self._guards.append((kind, tests))
        for item in nodes:
            self.visit(item)
        self._guards.pop()

    def visit_If(self, node: ast.If) -> None:
        """Visit both branches under the condition that selects them."""
        self.visit(node.test)
        self._guarded('if', (node.test,), node.body)
        self._guarded('else', (node.test,), node.orelse)

    def visit_While(self, node: ast.While) -> None:
        """Visit the loop and its ``else`` under the loop condition."""
        self.visit(node.test)
        self._guarded('while', (node.test,), node.body)
        self._guarded('else', (node.test,), node.orelse)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        """Visit both values of a conditional expression under its test."""
        self.visit(node.test)
        self._guarded('if', (node.test,), [node.body])
        self._guarded('else', (node.test,), [node.orelse])

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Visit each operand under the operands evaluated before it."""
        kind = type(node.op).__name__.lower()
        self.visit(node.values[0])
        for index in range(1, len(node.values)):
            preceding = tuple(node.values[:index])
            self._guarded(kind, preceding, [node.values[index]])

    def _try(self, node: ast.Try | ast.TryStar) -> None:
        """Visit each ``except`` clause under the exceptions it catches."""
        for item in (*node.body, *node.orelse, *node.finalbody):
            self.visit(item)
        for handler in node.handlers:
            caught: tuple[ast.expr, ...] = ()
            if handler.type is not None:
                self.visit(handler.type)
                caught = (handler.type,)
            self._guarded('except', caught, handler.body)

    def visit_Try(self, node: ast.Try) -> None:
        """Visit a ``try`` statement and its handlers."""
        self._try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        """Visit a ``try``/``except*`` statement and its handlers."""
        self._try(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        """Report a raised skip exception, which skips the running test."""
        exception = node.exc
        if exception is not None:
            raised = (
                exception.func
                if isinstance(exception, ast.Call)
                else exception
            )
            classification = self._classification(raised)
            if classification is not None and classification.raised_only:
                self._emit_classified(classification, exception)
                if isinstance(exception, ast.Call):
                    for child in (*exception.args, *exception.keywords):
                        self.visit(child)
            else:
                self.visit(exception)
        if node.cause is not None:
            self.visit(node.cause)

    def visit_Call(self, node: ast.Call) -> None:
        """Report a skip call or marker once, at the whole call."""
        classification = self._classification(node.func)
        if classification is not None:
            if not classification.raised_only:
                self._emit_classified(classification, node)
            for child in (*node.args, *node.keywords):
                self.visit(child)
            return
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr in _LIST_MUTATIONS
            and isinstance(function.value, ast.Name)
            and function.value.id in COLLECTION_LISTS
        ):
            entries = (
                self._collection_entries(node.args[:1], node)
                if function.attr == 'extend'
                else iter([node])
            )
            for entry in entries:
                self._emit(function.value.id, entry, deselection=True)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Report a skip-capable attribute without its inner chain."""
        classification = self._classification(node)
        if classification is None:
            self.generic_visit(node)
        elif not classification.raised_only:
            self._emit_classified(classification, node)

    def visit_Name(self, node: ast.Name) -> None:
        """Report an imported or aliased skip-capable name."""
        classification = self._classification(node)
        if classification is not None and not classification.raised_only:
            self._emit_classified(classification, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Report each entry assigned to a collection-ignore list."""
        self._collection_assignment(node.targets, node.value, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Report each entry added to a collection-ignore list."""
        self._collection_assignment([node.target], node.value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Report each entry of an annotated collection-ignore list."""
        if node.value is not None:
            self._collection_assignment([node.target], node.value, node)
        self.generic_visit(node)

    def _collection_assignment(
        self, targets: list[ast.expr], value: ast.expr, statement: ast.stmt
    ) -> None:
        """Emit one signal per entry assigned to ``collect_ignore``."""
        for target in targets:
            if isinstance(target, ast.Name) and target.id in COLLECTION_LISTS:
                for entry in self._collection_entries([value], statement):
                    self._emit(target.id, entry, deselection=True)

    @staticmethod
    def _collection_entries(
        values: list[ast.expr], statement: ast.AST
    ) -> Iterator[ast.AST]:
        """Yield literal entries, or the statement for computed values."""
        for value in values:
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                yield from value.elts
            else:
                yield statement


def collect_signals(
    source: str, deselected: frozenset[str]
) -> dict[str, list[Signal]]:
    """Return the signals each module, class, and function declares."""
    tree = ast.parse(source)
    return _SignalCollector(source.splitlines(), deselected).collect(tree)
