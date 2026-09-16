"""Shared semantic rules for the repository documentation corpus."""

from __future__ import annotations

import ast
import re
from pathlib import Path

DISALLOWED_SYMBOLS = {
    'GlobalDataFinanceError',
    'download_single',
    'download_files',
    'get_logging_settings',
}
KNOWN_IMPORTS: dict[str, set[str]] = {
    'globaldatafinance': {
        'FundamentalStocksDataCVM',
        'HistoricalQuotesB3',
        'ExtractionResultB3',
    },
    'globaldatafinance.core': {
        'ResourceLimits',
        'setup_logging',
        'get_logger',
        'is_logging_configured',
        'log_execution_time',
        'log_with_context',
        'ResourceMonitor',
        'ResourceState',
        'RetryStrategy',
    },
    'globaldatafinance.core.config': {
        'ArchiveSafetySettings',
        'NetworkSettings',
        'PathSafetySettings',
        'Settings',
    },
    'globaldatafinance.core.logging_config': {
        'ContextFilter',
        'LoggingSettings',
        'StructuredFormatter',
        'get_logger',
        'is_logging_configured',
        'log_execution_time',
        'log_with_context',
        'setup_logging',
    },
    'globaldatafinance.brazil.cvm.fundamental_stocks_data.client': {
        'DownloadDocumentsUseCaseCVM',
    },
    'globaldatafinance.brazil.cvm.fundamental_stocks_data.core': {
        'DownloadResultCVM',
        'AvailableYearsInfoCVM',
        'AvailableYearsCVM',
        'get_url_docs',
        'validate_docs_name',
    },
    'globaldatafinance.brazil.cvm.fundamental_stocks_data.http': {
        'AsyncDownloadAdapterCVM',
        'DownloadTaskCVM',
    },
    'globaldatafinance.brazil.cvm.fundamental_stocks_data.errors': {
        'CvmError',
        'InvalidFirstYear',
        'InvalidLastYear',
        'InvalidDocumentName',
        'InvalidDocumentType',
        'EmptyDocumentListError',
        'MissingDownloadUrlError',
    },
    'globaldatafinance.brazil.b3_data.historical_quotes.errors': {
        'InvalidFirstYear',
        'InvalidLastYear',
        'InvalidAssetsName',
        'EmptyAssetListError',
        'InvalidProcessingMode',
        'InvalidOutputFilename',
    },
    'globaldatafinance.macro_exceptions': {
        'EmptyDirectoryError',
        'InvalidDestinationPathError',
        'PathIsNotDirectoryError',
        'PathPermissionError',
        'PathCreationError',
        'FileWriteError',
        'ParquetWriteError',
        'DiskFullError',
        'ExtractionError',
        'CorruptedZipError',
        'SecurityError',
        'NetworkError',
        'TimeoutError',
    },
}

B3_MODULE_README = (
    'src/globaldatafinance/brazil/b3_data/historical_quotes/README.md'
)
CVM_MODULE_README = (
    'src/globaldatafinance/brazil/cvm/fundamental_stocks_data/README.md'
)
ROOT_README = (Path(__file__).resolve().parents[1] / 'README.md').as_posix()
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_B3_PATHS = frozenset(
    {
        ROOT_README,
        'docs/index.md',
        'docs/index.en.md',
        'docs/user-guide/b3-docs.md',
        'docs/user-guide/b3-docs.en.md',
        'docs/user-guide/quickstart.md',
        'docs/user-guide/quickstart.en.md',
        'docs/user-guide/faq.md',
        'docs/user-guide/faq.en.md',
        'docs/reference/b3-api.md',
        'docs/reference/b3-api.en.md',
        'docs/dev-guide/api-reference.md',
        'docs/dev-guide/api-reference.en.md',
        'docs/dev-guide/architecture.md',
        'docs/dev-guide/architecture.en.md',
        'docs/dev-guide/advanced-usage.md',
        'docs/dev-guide/advanced-usage.en.md',
        B3_MODULE_README,
        'examples/README.md',
    }
)
CONTRACT_MARKERS: dict[str, re.Pattern[str]] = {
    marker: re.compile(re.escape(marker), re.IGNORECASE)
    for marker in (
        'COTAHIST',
        'ZIP',
        'TXT',
        '010',
        '020',
        'total_files',
        'success_count',
        'error_count',
        'successful_downloads',
        'failed_downloads',
        'file_target',
    )
}

_POSITIVE_B3_SUPPORT = re.compile(
    r'(?is)(?:\bZIP\s*(?:/|or|ou)\s*TXT\b|\bTXT\s*(?:/|or|ou)\s*ZIP\b|'
    r'\b(?:accepts?|supports?|reads?|parses?|processes?|extracts?|'
    r'aceita[mn]?|suporta|l[eê]|analisa|processa|extrai|scanner|extrator)\b'
    r'[^\n]{0,180}\b(?:ZIP|TXT)\b[^\n]{0,180}\b(?:ZIP|TXT)\b)'
)
_ZIP_ONLY_CLAIM = re.compile(
    r'(?i)(?:\b(?:only|solely|exclusively|somente|apenas|exclusivamente)\b'
    r'[^\n]{0,100}\bZIP\b|\bZIP\b[^\n]{0,100}\b'
    r'(?:only|solely|exclusively|somente|apenas|exclusivamente)\b)'
)
_API_CONTEXT = re.compile(
    r'(?i)\b(?:api|extractor|scanner|reader|parser|process(?:es|a|am)?|'
    r'extract(?:s|or|ion)?|accept(?:s)?|support(?:s)?|read(?:s)?|'
    r'aceita[mn]?|suporta|l[eê]|analisa|processa|extrai)\b'
)
_ZIP_PRECEDENCE_CONTEXT = re.compile(
    r'(?i)\b(?:both|same\s+year|coexist|os\s+dois|ambos|coexistir|'
    r'mesmo\s+ano|precedência|precedence|prevalece|selecionad[oa])\b'
)


def documentation_files(repo_root: Path) -> list[Path]:
    """Return the explicit documentation corpus, including unpaired READMEs."""
    files = set((repo_root / 'docs').rglob('*.md'))
    for relative_path in (
        'README.md',
        'examples/README.md',
        B3_MODULE_README,
        CVM_MODULE_README,
    ):
        candidate = repo_root / relative_path
        if candidate.exists():
            files.add(candidate)
    return sorted(files)


def check_test_module_commands(
    file_path: Path,
    content: str,
    repo_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Ensure documented test modules exist in the repository."""
    errors: list[str] = []
    module_pattern = re.compile(
        r'\bpython(?:3(?:\.\d+)?)?\s+-m\s+'
        r'(tests(?:\.[A-Za-z_]\w*)+)\b'
    )
    for match in module_pattern.finditer(content):
        module_name = match.group(1)
        module_path = repo_root / Path(*module_name.split('.'))
        module_exists = (module_path.with_suffix('.py')).is_file() or (
            (module_path / '__init__.py').is_file()
        )
        if not module_exists:
            line_number = content.count('\n', 0, match.start()) + 1
            errors.append(
                f'{file_path}:{line_number}: documented test module does not '
                'exist: '
                f'{module_name}'
            )
    return errors


def _matches_public_path(file_path: Path, relative_path: str) -> bool:
    normalized = file_path.as_posix()
    if relative_path == ROOT_README:
        return (
            file_path == Path('README.md')
            or file_path.resolve().as_posix() == relative_path
        )
    return normalized == relative_path or normalized.endswith(
        f'/{relative_path}'
    )


def is_public_b3_document(file_path: Path) -> bool:
    """Return whether a path documents the public B3 input contract."""
    return any(
        _matches_public_path(file_path, path) for path in PUBLIC_B3_PATHS
    )


def check_public_b3_contract(file_path: Path, content: str) -> list[str]:
    """Check that public B3 docs distinguish ZIP downloads from TXT support."""
    if not is_public_b3_document(file_path):
        return []

    errors: list[str] = []
    if not re.search(r'COTAHIST_A', content, re.IGNORECASE):
        errors.append(
            f'{file_path}:1: public B3 documentation must name COTAHIST_A '
            'inputs'
        )
    if not re.search(r'\bZIP\b', content, re.IGNORECASE) or not re.search(
        r'\bTXT\b', content, re.IGNORECASE
    ):
        errors.append(
            f'{file_path}:1: public B3 documentation must mention both ZIP '
            'and TXT'
        )
    if not _POSITIVE_B3_SUPPORT.search(content):
        errors.append(
            f'{file_path}:1: public B3 documentation must state that the API '
            'accepts ZIP and TXT'
        )

    for line_number, line in enumerate(content.splitlines(), 1):
        if not _ZIP_ONLY_CLAIM.search(line):
            continue
        if _API_CONTEXT.search(line) and not _ZIP_PRECEDENCE_CONTEXT.search(
            line
        ):
            errors.append(
                f'{file_path}:{line_number}: B3 API/input contract must not '
                'claim ZIP-only support'
            )
    return errors


def check_bilingual_contract_markers(
    pt_file: Path, en_file: Path
) -> list[str]:
    """Ensure paired pages expose the same detectable contract markers."""
    pt_content = pt_file.read_text(encoding='utf-8')
    en_content = en_file.read_text(encoding='utf-8')
    pt_markers = {
        name
        for name, pattern in CONTRACT_MARKERS.items()
        if pattern.search(pt_content)
    }
    en_markers = {
        name
        for name, pattern in CONTRACT_MARKERS.items()
        if pattern.search(en_content)
    }
    errors: list[str] = []
    for marker in sorted(pt_markers - en_markers):
        errors.append(
            f'{pt_file}:1: contract marker {marker!r} missing from {en_file}'
        )
    for marker in sorted(en_markers - pt_markers):
        errors.append(
            f'{en_file}:1: contract marker {marker!r} missing from {pt_file}'
        )
    return errors


def _parse_logging_blocks(
    file_path: Path, code_blocks: list[tuple[int, str, str]]
) -> tuple[list[ast.Module], list[str]]:
    """Parse Python logging blocks and retain syntax diagnostics."""
    trees: list[ast.Module] = []
    errors: list[str] = []
    for _, lang, code in code_blocks:
        if lang.lower() not in ('python', 'py'):
            continue
        try:
            trees.append(ast.parse(code))
        except SyntaxError as exc:
            errors.append(
                f'{file_path}:{exc.lineno or 1}: SyntaxError in logging code '
                f'block: {exc.msg}'
            )
    return trees, errors


def _inspect_logging_keyword(
    file_path: Path,
    node: ast.Call,
    keyword: ast.keyword,
) -> tuple[list[str], bool]:
    """Inspect one logging keyword and its structured context dictionary."""
    errors: list[str] = []
    line_number = getattr(node, 'lineno', 1)
    if keyword.arg == 'filename':
        errors.append(
            f'{file_path}:{line_number}: reserved logging key filename is '
            'forbidden'
        )
    has_file_target = keyword.arg == 'file_target'
    if keyword.arg != 'extra' or not isinstance(keyword.value, ast.Dict):
        return errors, has_file_target

    for key in keyword.value.keys:
        if not isinstance(key, ast.Constant):
            continue
        if key.value == 'filename':
            errors.append(
                f'{file_path}:{line_number}: reserved logging key filename '
                'is forbidden'
            )
        if key.value == 'file_target':
            has_file_target = True
    return errors, has_file_target


def _inspect_logging_tree(
    file_path: Path, tree: ast.Module
) -> tuple[list[str], bool]:
    """Inspect all call keywords in one parsed logging example."""
    errors: list[str] = []
    has_file_target = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            keyword_errors, keyword_has_target = _inspect_logging_keyword(
                file_path, node, keyword
            )
            errors.extend(keyword_errors)
            has_file_target |= keyword_has_target
    return errors, has_file_target


def check_logging_contract(
    file_path: Path, code_blocks: list[tuple[int, str, str]]
) -> list[str]:
    """Check safe logging context usage and expose malformed Python blocks."""
    trees, errors = _parse_logging_blocks(file_path, code_blocks)
    has_semantic_file_target = False
    for tree in trees:
        tree_errors, tree_has_target = _inspect_logging_tree(file_path, tree)
        errors.extend(tree_errors)
        has_semantic_file_target |= tree_has_target
    if not has_semantic_file_target:
        errors.append(
            f'{file_path}:1: missing semantic file_target in logging context'
        )
    return errors
