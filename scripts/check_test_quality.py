#!/usr/bin/env python3
"""Check test-suite structural quality contracts with static heuristics."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PRIMARY_MARKERS = frozenset({'unit', 'integration', 'perf'})
REAL_DATA_MARKER = 'real_data'
NAME_MANGLED_PATTERN = re.compile(r'_[A-Za-z][A-Za-z0-9]*__[_A-Za-z0-9]+')


@dataclass(frozen=True)
class Finding:
    """One actionable structural test-quality diagnostic."""

    path: str
    line: int
    code: str
    message: str

    def render(self) -> str:
        """Render the finding in a stable file-and-line format."""
        return f'{self.path}:{self.line}: [{self.code}] {self.message}'


def _marker_name(node: ast.AST) -> str | None:
    """Return a pytest marker name from a marker expression."""
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute):
        return None
    parent = node.value
    if not isinstance(parent, ast.Attribute):
        return None
    if not isinstance(parent.value, ast.Name) or parent.value.id != 'pytest':
        return None
    if parent.attr != 'mark':
        return None
    return node.attr


def _markers_from_expression(node: ast.AST) -> set[str]:
    """Collect pytest marker names from a ``pytestmark`` expression."""
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        markers: set[str] = set()
        for element in node.elts:
            marker = _marker_name(element)
            if marker is not None:
                markers.add(marker)
        return markers

    marker = _marker_name(node)
    return {marker} if marker is not None else set()


def _module_markers(tree: ast.Module) -> set[str]:
    """Collect module-level markers used by pytest for every test."""
    markers: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            if any(
                isinstance(target, ast.Name) and target.id == 'pytestmark'
                for target in targets
            ):
                value = statement.value
                if value is not None:
                    markers.update(_markers_from_expression(value))
    return markers


def _decorator_markers(decorators: list[ast.expr]) -> set[str]:
    """Collect pytest markers attached to a class or test function."""
    markers: set[str] = set()
    for decorator in decorators:
        marker = _marker_name(decorator)
        if marker is not None:
            markers.add(marker)
    return markers


def _test_functions(
    statements: list[ast.stmt],
    inherited_markers: set[str],
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, set[str]]]:
    """Return test functions with markers inherited from enclosing classes."""
    functions: list[
        tuple[ast.FunctionDef | ast.AsyncFunctionDef, set[str]]
    ] = []
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            class_markers = inherited_markers | _decorator_markers(
                statement.decorator_list
            )
            functions.extend(_test_functions(statement.body, class_markers))
            continue

        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name.startswith('test_'):
                function_markers = inherited_markers | _decorator_markers(
                    statement.decorator_list
                )
                functions.append((statement, function_markers))
            continue

    return functions


def _body_without_docstring(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    """Return a test body without its optional leading docstring."""
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _has_accepted_assertion(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return whether a direct test body observes an accepted context."""
    return any(
        _contains_accepted_assertion(statement)
        for statement in _body_without_docstring(node)
    )


def _contains_accepted_assertion(node: ast.AST) -> bool:
    """Inspect executable descendants without entering nested definitions."""
    if isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef),
    ):
        return False

    if isinstance(node, ast.Assert):
        return True

    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Attribute):
            if (
                function.attr in {'raises', 'warns'}
                and isinstance(function.value, ast.Name)
                and function.value.id == 'pytest'
            ):
                return True
            if function.attr.startswith('assert'):
                return True

    return any(
        _contains_accepted_assertion(child)
        for child in ast.iter_child_nodes(node)
    )


def _is_noop_body(body: list[ast.stmt]) -> bool:
    """Return whether a test body contains only no-op statements."""
    if not body:
        return True
    return all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
        )
        for statement in body
    )


def _is_name_mangled(name: str) -> bool:
    """Return whether a name has Python's class-private mangled shape."""
    return NAME_MANGLED_PATTERN.fullmatch(name) is not None


def _finding(
    path: str,
    node: ast.AST,
    code: str,
    message: str,
) -> Finding:
    """Build a finding using the source line of an AST node."""
    return Finding(path, getattr(node, 'lineno', 1), code, message)


def _test_contract_findings(
    path: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    markers: set[str],
) -> list[Finding]:
    """Find missing tier, observability, and non-empty test contracts."""
    findings: list[Finding] = []
    primary = sorted(markers & PRIMARY_MARKERS)
    if len(primary) != 1:
        if primary:
            details = ', '.join(primary)
            message = (
                'Keep exactly one primary marker (unit, integration, or '
                f'perf); found: {details}.'
            )
        else:
            message = (
                'Add exactly one primary marker: '
                '@pytest.mark.unit, @pytest.mark.integration, or '
                '@pytest.mark.perf.'
            )
        findings.append(_finding(path, function, 'PRIMARY_TIER', message))

    if REAL_DATA_MARKER in markers and 'integration' not in markers:
        findings.append(
            _finding(
                path,
                function,
                'REAL_DATA_TIER',
                'Combine real_data with the integration primary marker.',
            )
        )

    body = _body_without_docstring(function)
    if _is_noop_body(body):
        findings.append(
            _finding(
                path,
                function,
                'NOOP_TEST',
                'Replace the empty test with an observable regression or '
                'remove it.',
            )
        )

    if not _has_accepted_assertion(function):
        findings.append(
            _finding(
                path,
                function,
                'ASSERTION',
                'Add an assertion, pytest.raises/pytest.warns context, '
                'or mock/spy assert_* call that proves the behavior.',
            )
        )
    return findings


def _structural_findings(path: str, tree: ast.Module) -> list[Finding]:
    """Find debug output and private name-mangled seams in a test module."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'print':
                findings.append(
                    _finding(
                        path,
                        node,
                        'RAW_PRINT',
                        'Remove print() from tests; use assertions, caplog, '
                        'pytest failure output.',
                    )
                )
            if isinstance(node.func, ast.Attribute) and _is_name_mangled(
                node.func.attr
            ):
                findings.append(
                    _finding(
                        path,
                        node,
                        'NAME_MANGLED',
                        'Use a public behavior seam instead of a '
                        'name-mangled private attribute.',
                    )
                )
        elif isinstance(node, ast.Attribute) and _is_name_mangled(node.attr):
            findings.append(
                _finding(
                    path,
                    node,
                    'NAME_MANGLED',
                    'Use a public behavior seam instead of a name-mangled '
                    'private attribute.',
                )
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if NAME_MANGLED_PATTERN.search(node.value):
                findings.append(
                    _finding(
                        path,
                        node,
                        'NAME_MANGLED',
                        'Do not encode name-mangled private attributes in '
                        'patch paths or test data.',
                    )
                )
    return findings


def inspect_test_file(path: Path) -> list[Finding]:
    """Inspect one Python test module without importing or executing it."""
    display_path = path.as_posix()
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        line = getattr(error, 'lineno', 1) or 1
        return [
            Finding(
                display_path,
                line,
                'PARSE',
                f'Fix the test module syntax/encoding before rerunning: '
                f'{error}',
            )
        ]

    module_markers = _module_markers(tree)
    findings = [
        finding
        for function, markers in _test_functions(tree.body, module_markers)
        for finding in _test_contract_findings(display_path, function, markers)
    ]
    findings.extend(_structural_findings(display_path, tree))
    return findings


def _python_files(paths: list[str]) -> list[Path]:
    """Resolve requested files/directories into a deterministic Python list."""
    files: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f'Path does not exist: {path}')
        if path.is_file():
            if path.suffix == '.py':
                files.add(path)
            continue
        files.update(
            candidate
            for candidate in path.rglob('*.py')
            if '__pycache__' not in candidate.parts
        )
    return sorted(files, key=lambda item: item.as_posix())


def main(argv: list[str] | None = None) -> int:
    """Run the AST test-quality gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'paths',
        nargs='*',
        default=['tests'],
        help='Python test files or directories (default: tests).',
    )
    args = parser.parse_args(argv)

    try:
        files = _python_files(args.paths)
        findings = [
            finding for path in files for finding in inspect_test_file(path)
        ]
    except (FileNotFoundError, OSError) as error:
        print(f'ERROR [TEST_QUALITY]: {error}', file=sys.stderr)
        return 2

    findings.sort(key=lambda item: (item.path, item.line, item.code))
    if findings:
        print(
            'FAIL [TEST_QUALITY]: Structural test-quality violations:',
            file=sys.stderr,
        )
        for finding in findings:
            print(f'  • {finding.render()}', file=sys.stderr)
        print(
            '\nResolution: classify each test with exactly one primary tier, '
            'make its behavior observable, and remove private/debug seams.',
            file=sys.stderr,
        )
        return 1

    print(f'PASS [TEST_QUALITY]: Inspected {len(files)} Python files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
