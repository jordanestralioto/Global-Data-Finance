"""Validate semantic contracts inside documentation code-block ASTs."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.docs_contract_ast import SourceContracts
from scripts.docs_contract_rules import DISALLOWED_SYMBOLS, KNOWN_IMPORTS


class _AstBlockState:
    """Track cross-node facts discovered in one documentation code block."""

    def __init__(self) -> None:
        self.has_b3_import = False
        self.has_b3_instantiation = False
        self.has_b3_extract_call = False
        self.has_cvm_adapter = False
        self.has_cvm_download_method = False


def _check_class_node(
    node: ast.AST,
    contracts: SourceContracts,
    state: _AstBlockState,
) -> None:
    """Record the documented CVM adapter and its download method."""
    if not (
        isinstance(node, ast.ClassDef) and node.name == 'CvmDownloadAdapter'
    ):
        return
    state.has_cvm_adapter = True
    state.has_cvm_download_method = any(
        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        and member.name == contracts.cvm_download_method
        for member in node.body
    )


def _check_import_node(
    file_path: Path,
    node: ast.AST,
    node_line: int,
    state: _AstBlockState,
) -> list[str]:
    """Inspect one import for known and disallowed documentation symbols."""
    if not isinstance(node, ast.ImportFrom):
        return []
    errors: list[str] = []
    module_name = node.module or ''
    for alias in node.names:
        if alias.name == 'HistoricalQuotesB3':
            state.has_b3_import = True
        if alias.name in DISALLOWED_SYMBOLS:
            errors.append(
                f'{file_path}:{node_line}: '
                f'disallowed symbol imported: {alias.name}'
            )
        if (
            module_name in KNOWN_IMPORTS
            and alias.name not in KNOWN_IMPORTS[module_name]
        ):
            errors.append(
                f'{file_path}:{node_line}: symbol {alias.name} not found in '
                f'module {module_name}'
            )
    return errors


def _check_assignment_node(node: ast.AST, state: _AstBlockState) -> None:
    """Record construction of the public B3 facade."""
    if (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'HistoricalQuotesB3'
    ):
        state.has_b3_instantiation = True


def _check_attribute_node(
    file_path: Path, node: ast.AST, node_line: int
) -> list[str]:
    """Reject disallowed documented attributes and methods."""
    if isinstance(node, ast.Attribute) and node.attr in DISALLOWED_SYMBOLS:
        return [
            f'{file_path}:{node_line}: disallowed attribute or method used: '
            f'{node.attr}'
        ]
    return []


def _check_function_node(
    file_path: Path,
    node: ast.AST,
    node_line: int,
    contracts: SourceContracts,
) -> list[str]:
    """Reject stale CVM adapter stub method names."""
    if isinstance(node, ast.FunctionDef) and node.name in DISALLOWED_SYMBOLS:
        return [
            f'{file_path}:{node_line}: CVM adapter stub should use '
            f'{contracts.cvm_download_method}, not {node.name}'
        ]
    return []


def _check_dag_call(
    file_path: Path, node: ast.Call, node_line: int
) -> list[str]:
    """Reject incomplete DAG placeholders in executable examples."""
    if not (isinstance(node.func, ast.Name) and node.func.id == 'DAG'):
        return []
    if any(
        isinstance(argument, ast.Constant) and argument.value == Ellipsis
        for argument in node.args
    ):
        return [f'{file_path}:{node_line}: incomplete DAG placeholder (...)']
    return []


def _check_b3_extract_call(
    file_path: Path,
    node: ast.Call,
    node_line: int,
    state: _AstBlockState,
) -> list[str]:
    """Validate the required inputs of a documented B3 extraction call."""
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in ('extract', 'extract_async')
    ):
        return []
    state.has_b3_extract_call = True
    keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg}
    has_path = len(node.args) >= 1 or 'path_of_docs' in keyword_names
    has_assets = len(node.args) >= 2 or 'assets_list' in keyword_names
    if has_path and has_assets:
        return []
    return [
        f'{file_path}:{node_line}: b3.{node.func.attr}() call missing '
        'path_of_docs or assets_list'
    ]


def _check_call_node(
    file_path: Path,
    node: ast.AST,
    node_line: int,
    state: _AstBlockState,
) -> list[str]:
    """Inspect one call for disallowed symbols and incomplete contracts."""
    if not isinstance(node, ast.Call):
        return []
    errors: list[str] = []
    if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_SYMBOLS:
        errors.append(
            f'{file_path}:{node_line}: disallowed function called directly: '
            f'{node.func.id}'
        )
    errors.extend(_check_dag_call(file_path, node, node_line))
    errors.extend(_check_b3_extract_call(file_path, node, node_line, state))
    return errors


def check_ast_nodes(
    file_path: Path,
    start_line: int,
    tree: ast.AST,
    code: str,
    contracts: SourceContracts,
) -> list[str]:
    """Inspect AST nodes for contracts, disallowed calls, and context."""
    errors: list[str] = []
    state = _AstBlockState()

    for node in ast.walk(tree):
        node_line = start_line + getattr(node, 'lineno', 1) - 1
        _check_class_node(node, contracts, state)
        errors.extend(_check_import_node(file_path, node, node_line, state))
        _check_assignment_node(node, state)
        errors.extend(_check_attribute_node(file_path, node, node_line))
        errors.extend(
            _check_function_node(file_path, node, node_line, contracts)
        )
        errors.extend(_check_call_node(file_path, node, node_line, state))

    if state.has_cvm_adapter and not state.has_cvm_download_method:
        errors.append(
            f'{file_path}:{start_line}: CVM adapter documentation must expose '
            f'{contracts.cvm_download_method}()'
        )

    if (
        state.has_b3_extract_call
        and not (state.has_b3_import and state.has_b3_instantiation)
        and 'class ' not in code
        and 'def ' not in code
    ):
        errors.append(
            f'{file_path}:{start_line}: b3.extract() call without '
            'HistoricalQuotesB3 import or instantiation'
        )

    return errors
