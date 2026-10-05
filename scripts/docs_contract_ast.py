"""Extract runtime contracts from source without importing the package."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParameterContract:
    """Represent one public parameter and its source-level default."""

    name: str
    has_default: bool
    default: str | None


@dataclass(frozen=True)
class SourceContracts:
    """Public source contracts consumed by the documentation checker."""

    b3_extract_parameters: tuple[ParameterContract, ...]
    b3_asset_tpmerc_codes: tuple[tuple[str, tuple[str, ...]], ...]
    extraction_result_fields: tuple[str, ...]
    download_result_fields: tuple[str, ...]
    download_result_properties: tuple[str, ...]
    available_years_attributes: tuple[str, ...]
    cvm_download_method: str
    exception_names: frozenset[str]


def _parse_source(path: Path) -> ast.Module:
    """Parse one source module and preserve syntax errors for the caller."""
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    """Find a named class in a parsed module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ValueError(f'Class {name!r} was not found in the source module')


def _find_method(
    class_node: ast.ClassDef, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Find a regular or asynchronous method in a class body."""
    for node in class_node.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    raise ValueError(
        f'Method {name!r} was not found in class {class_node.name!r}'
    )


def _default_text(node: ast.expr) -> str:
    """Return a stable, source-independent representation of a default."""
    try:
        return repr(ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError):
        return ast.unparse(node)


def extract_parameters(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ParameterContract, ...]:
    """Extract positional and keyword-only parameter contracts."""
    positional = [*method.args.posonlyargs, *method.args.args]
    positional_defaults = [None] * (
        len(positional) - len(method.args.defaults)
    ) + list(method.args.defaults)
    parameters = [
        ParameterContract(
            name=argument.arg,
            has_default=default is not None,
            default=None if default is None else _default_text(default),
        )
        for argument, default in zip(
            positional, positional_defaults, strict=True
        )
        if argument.arg != 'self'
    ]

    for argument, default in zip(
        method.args.kwonlyargs, method.args.kw_defaults, strict=True
    ):
        parameters.append(
            ParameterContract(
                name=argument.arg,
                has_default=default is not None,
                default=None if default is None else _default_text(default),
            )
        )
    return tuple(parameters)


def _find_documented_extract(
    code_blocks: list[tuple[int, str, str]],
) -> tuple[int, ast.FunctionDef | ast.AsyncFunctionDef] | None:
    """Locate the first valid documented B3 extraction signature."""
    for start_line, lang, code in code_blocks:
        if lang.lower() not in ('python', 'py'):
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == 'extract'
            ):
                return start_line, node
    return None


def _compare_parameter_names(
    file_path: Path,
    line_number: int,
    expected: tuple[ParameterContract, ...],
    documented: tuple[ParameterContract, ...],
) -> list[str]:
    """Compare documented B3 parameter names and source ordering."""
    expected_names = tuple(parameter.name for parameter in expected)
    documented_names = tuple(parameter.name for parameter in documented)
    if documented_names == expected_names:
        return []
    return [
        f'{file_path}:{line_number}: HistoricalQuotesB3.extract parameter '
        'names/order do not match source '
        f'(expected {[p.name for p in expected]}, '
        f'got {[p.name for p in documented]})'
    ]


def _compare_parameter_defaults(
    file_path: Path,
    line_number: int,
    expected: tuple[ParameterContract, ...],
    documented: tuple[ParameterContract, ...],
) -> list[str]:
    """Compare presence and values of documented B3 defaults."""
    errors: list[str] = []
    for expected_parameter, documented_parameter in zip(
        expected, documented, strict=False
    ):
        if expected_parameter.has_default != documented_parameter.has_default:
            errors.append(
                f'{file_path}:{line_number}: extract signature default '
                f'presence for `{expected_parameter.name}` does not match '
                'source'
            )
        elif (
            expected_parameter.has_default
            and expected_parameter.default != documented_parameter.default
        ):
            errors.append(
                f'{file_path}:{line_number}: extract signature default for '
                f'`{expected_parameter.name}` differs from source '
                f'({expected_parameter.default!r} expected)'
            )
    return errors


def compare_documented_extract_signature(
    file_path: Path,
    code_blocks: list[tuple[int, str, str]],
    contracts: SourceContracts,
) -> list[str]:
    """Compare a documented B3 extraction signature to its source contract."""
    located = _find_documented_extract(code_blocks)
    if located is None:
        return [
            f'{file_path}:1: canonical B3 API documentation must include the '
            'HistoricalQuotesB3.extract signature'
        ]

    start_line, node = located
    line_number = start_line + node.lineno - 1
    documented = extract_parameters(node)
    expected = contracts.b3_extract_parameters
    return _compare_parameter_names(
        file_path, line_number, expected, documented
    ) + _compare_parameter_defaults(
        file_path, line_number, expected, documented
    )


def _annotated_names(class_node: ast.ClassDef) -> tuple[str, ...]:
    """Extract declared annotated attributes in source order."""
    return tuple(
        node.target.id
        for node in class_node.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and not node.target.id.startswith('_')
    )


def _property_names(class_node: ast.ClassDef) -> tuple[str, ...]:
    """Extract public methods decorated with ``@property``."""
    names: list[str] = []
    for node in class_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith('_'):
            continue
        if any(
            isinstance(decorator, ast.Name) and decorator.id == 'property'
            for decorator in node.decorator_list
        ):
            names.append(node.name)
    return tuple(names)


def _asset_tpmerc_codes(
    class_node: ast.ClassDef,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Extract the source mapping between asset aliases and TPMERC codes."""
    for node in class_node.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value

        if not (
            isinstance(target, ast.Name)
            and target.id == '_AVAILABLE_ASSETS_BY_CLASS'
            and value is not None
        ):
            continue

        mapping = ast.literal_eval(value)
        if not isinstance(mapping, dict):
            raise ValueError('_AVAILABLE_ASSETS_BY_CLASS must be a dict')
        return tuple(
            (str(asset), tuple(str(code) for code in codes))
            for asset, codes in mapping.items()
        )

    raise ValueError(
        'Class does not declare _AVAILABLE_ASSETS_BY_CLASS source mapping'
    )


def _exception_names(source_root: Path) -> frozenset[str]:
    """Collect exception-like classes declared by the source package."""
    names = {
        'Exception',
        'MemoryError',
        'OSError',
        'PermissionError',
        'RuntimeError',
        'TypeError',
        'ValueError',
    }
    exception_pattern = re.compile(r'(?:Error|Exception)$')
    for path in source_root.rglob('*.py'):
        tree = _parse_source(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if exception_pattern.search(node.name) or node.name.startswith(
                'Invalid'
            ):
                names.add(node.name)
    return frozenset(names)


def load_source_contracts(repo_root: Path) -> SourceContracts:
    """Build documentation contracts from the repository's source tree."""
    package_root = repo_root / 'src' / 'globaldatafinance'
    b3_facade = _parse_source(
        package_root
        / 'application'
        / 'b3_docs'
        / 'historical_quotes'
        / 'facade.py'
    )
    b3_types = _parse_source(
        package_root / 'application' / 'b3_docs' / 'types.py'
    )
    b3_assets = _parse_source(
        package_root / 'brazil' / 'b3_data' / 'historical_quotes' / 'assets.py'
    )
    cvm_core = _parse_source(
        package_root / 'brazil' / 'cvm' / 'fundamental_stocks_data' / 'core.py'
    )
    cvm_http = _parse_source(
        package_root / 'brazil' / 'cvm' / 'fundamental_stocks_data' / 'http.py'
    )

    b3_extract = _find_method(
        _find_class(b3_facade, 'HistoricalQuotesB3'), 'extract'
    )
    b3_asset_service = _find_class(b3_assets, 'AvailableAssetsServiceB3')
    extraction_result = _find_class(b3_types, 'ExtractionResultB3')
    download_result = _find_class(cvm_core, 'DownloadResultCVM')
    available_years = _find_class(cvm_core, 'AvailableYearsInfoCVM')
    cvm_adapter = _find_class(cvm_http, 'AsyncDownloadAdapterCVM')

    return SourceContracts(
        b3_extract_parameters=extract_parameters(b3_extract),
        b3_asset_tpmerc_codes=_asset_tpmerc_codes(b3_asset_service),
        extraction_result_fields=_annotated_names(extraction_result),
        download_result_fields=_annotated_names(download_result),
        download_result_properties=_property_names(download_result),
        available_years_attributes=_annotated_names(available_years),
        cvm_download_method=_find_method(cvm_adapter, 'download_docs').name,
        exception_names=_exception_names(package_root),
    )
