"""Semantic rules for public API documentation contracts."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.docs_contract_ast import (
    SourceContracts,
    compare_documented_extract_signature,
)
from scripts.docs_contract_rules import (
    B3_MODULE_READMES,
    PUBLIC_B3_PATHS,
    _matches_public_path,
)

PUBLIC_B3_API_PATHS = frozenset(
    {
        'docs/reference/b3-api.md',
        'docs/reference/b3-api.en.md',
        'docs/dev-guide/api-reference.md',
        'docs/dev-guide/api-reference.en.md',
    }
)
PUBLIC_CVM_API_PATHS = frozenset(
    {
        'docs/reference/cvm-api.md',
        'docs/reference/cvm-api.en.md',
    }
)
PUBLIC_B3_ASSET_PATHS = PUBLIC_B3_PATHS | frozenset(
    {
        'docs/user-guide/examples.md',
        'docs/user-guide/examples.en.md',
    }
)
_SPOT_MARKET = re.compile(
    r'(?i)\bspot(?:\s+cash)?\s+market\b|mercado\s+à\s+vista'
)
_FRACTIONAL_MARKET = re.compile(r'(?i)\bfractional\b|fracionári[oa]|\b020\b')
_ASSET_CLASS_TERMS: dict[str, tuple[str, ...]] = {
    'ações': ('ações', 'stock', 'stocks', 'equity', 'equities'),
    'etf': ('etf', 'etfs'),
}
_MODEL_VALIDATION_CLAIM = re.compile(
    r'(?i)(?:encapsula(?:m)?\s+e\s+valida|valida\s+automaticamente|'
    r'validates?\s+(?:the\s+)?(?:parameters|types|paths|configuration)|'
    r'valida\s+(?:os\s+)?(?:parâmetros|tipos|caminhos|configuração))'
)
_TICKER_REFERENCE = re.compile(r'(?i)\btickers?\b')
_DOCUMENT_NAME_CLAIM = re.compile(
    r'(?i)documents_to_download[^\n]{0,180}'
    r'(?:exact\s+(?:file\s+)?names?|file\s+names?|nomes?\s+exatos?'
    r'(?:\s+dos\s+arquivos?)?|nomes?\s+de\s+arquivos?)'
)
_DIRECT_BASENAME_SET = re.compile(
    r'(?is)documents_to_download\s*=\s*\{\s*["\'][^/\\\n]+\.(?:zip|txt)'
)


def is_public_b3_api_document(file_path: Path) -> bool:
    """Return whether a path is one of the canonical B3 API references."""
    return any(
        _matches_public_path(file_path, path) for path in PUBLIC_B3_API_PATHS
    )


def is_public_cvm_api_document(file_path: Path) -> bool:
    """Return whether a path is a canonical CVM API reference."""
    return any(
        _matches_public_path(file_path, path) for path in PUBLIC_CVM_API_PATHS
    )


def _aliases_with_code(
    contracts: SourceContracts, code: str
) -> tuple[str, ...]:
    """Return asset aliases mapped to one source-level TPMERC code."""
    return tuple(
        alias
        for alias, codes in contracts.b3_asset_tpmerc_codes
        if code in codes
    )


def _has_asset_class_context(line: str, aliases: tuple[str, ...]) -> bool:
    """Detect language referring to one of the mapped asset classes."""
    normalized = line.casefold()
    return any(
        term.casefold() in normalized
        for alias in aliases
        for term in _ASSET_CLASS_TERMS.get(alias, (alias,))
    )


def _normalized_paragraphs(content: str) -> list[tuple[int, str]]:
    """Return non-empty paragraphs with their source line numbers."""
    paragraphs: list[tuple[int, str]] = []
    offset = 0
    for block in re.split(r'\n\s*\n', content):
        start = content.find(block, offset)
        if start < 0:
            continue
        offset = start + len(block)
        if not block.strip():
            continue
        paragraphs.append(
            (
                content.count('\n', 0, start) + 1,
                re.sub(r'\s+', ' ', block),
            )
        )
    return paragraphs


def check_public_b3_asset_semantics(
    file_path: Path,
    content: str,
    contracts: SourceContracts,
) -> list[str]:
    """Reject claims that mapped stock classes select only the spot market."""
    if not any(
        _matches_public_path(file_path, path) for path in PUBLIC_B3_ASSET_PATHS
    ):
        return []

    stock_aliases = _aliases_with_code(contracts, '020')
    errors: list[str] = []
    for line_number, paragraph in _normalized_paragraphs(content):
        if not _SPOT_MARKET.search(paragraph) or not _has_asset_class_context(
            paragraph, stock_aliases
        ):
            continue
        if not _FRACTIONAL_MARKET.search(paragraph):
            errors.append(
                f'{file_path}:{line_number}: B3 asset-class docs must '
                'not describe mapped stock/ETF aliases as spot-only; they '
                'select '
                'TPMERC 010 and 020'
            )
    return errors


def check_b3_internal_readme_contract(
    file_path: Path,
    content: str,
) -> list[str]:
    """Check ownership and path semantics for internal B3 objects."""
    if not any(
        _matches_public_path(file_path, path) for path in B3_MODULE_READMES
    ):
        return []

    errors: list[str] = []
    lines = content.splitlines()
    for line_number, line in enumerate(lines, 1):
        if (
            'CreateDocsToExtractUseCaseB3' not in line
            and 'DocsToExtractorB3' in line
            and _MODEL_VALIDATION_CLAIM.search(line)
        ):
            errors.append(
                f'{file_path}:{line_number}: DocsToExtractorB3 must be '
                'documented '
                'as a data object without direct validation'
            )
    if not re.search(
        r'(?is)DocsToExtractorB3.{0,180}(?:data object|não executa validação|'
        r'nao executa validacao|does not .*validat)',
        content,
    ):
        errors.append(
            f'{file_path}:1: B3 README must state that DocsToExtractorB3 is a '
            'data object and does not validate direct construction'
        )
    create_contexts = [
        content[match.start() : match.start() + 300]
        for match in re.finditer('CreateDocsToExtractUseCaseB3', content)
    ]
    if not any(
        re.search(r'(?i)validat|valida', context)
        and re.search(
            r'(?i)construct|constrói|constroi|resolve|prepara', context
        )
        for context in create_contexts
    ):
        errors.append(
            f'{file_path}:1: B3 README must assign input validation and '
            'configuration construction to CreateDocsToExtractUseCaseB3'
        )
    if _TICKER_REFERENCE.search(content):
        errors.append(
            f'{file_path}:1: B3 README must call ações/etf/opções asset '
            'classes '
            'or aliases, not individual tickers'
        )
    if _DOCUMENT_NAME_CLAIM.search(content) or _DIRECT_BASENAME_SET.search(
        content
    ):
        errors.append(
            f'{file_path}:1: B3 README must not document '
            'documents_to_download '
            'as a set of bare filenames'
        )
    if not re.search(
        r'(?is)documents_to_download.{0,240}'
        r'(?:absolute paths|caminhos absolutos)',
        content,
    ):
        errors.append(
            f'{file_path}:1: B3 README must document documents_to_download '
            'as resolved absolute paths'
        )
    if not re.search(r'(?i)classes?\s+de\s+ativos|asset\s+classes?', content):
        errors.append(
            f'{file_path}:1: B3 README must use asset-class terminology'
        )
    return errors


def _missing_markers(
    file_path: Path,
    content: str,
    markers: tuple[str, ...],
    contract_name: str,
) -> list[str]:
    """Report source contract names that are absent from a document."""
    errors: list[str] = []
    for marker in markers:
        if not re.search(
            rf'(?m)^\s*(?:[-*]|\|).*?'
            rf'(?:`{re.escape(marker)}`|\b{re.escape(marker)}\b)',
            content,
        ):
            errors.append(
                f'{file_path}:1: {contract_name} must document `{marker}`'
            )
    return errors


def check_public_b3_api_contract(
    file_path: Path,
    content: str,
    contracts: SourceContracts,
) -> list[str]:
    """Validate canonical B3 result, input, and empty-result contracts."""
    if not is_public_b3_api_document(file_path):
        return []

    errors = _missing_markers(
        file_path,
        content,
        contracts.extraction_result_fields,
        'ExtractionResultB3',
    )
    errors.extend(_check_b3_catalog_semantics(file_path, content))

    output_contract = re.search(
        r'(?is)output_filename.{0,240}basename.{0,240}\.parquet', content
    )
    if output_contract is None:
        errors.append(
            f'{file_path}:1: B3 API docs must describe output_filename '
            'as a basename with an optional .parquet suffix'
        )
    if not re.search(
        r'(?is)(?:optional|opcional).{0,180}(?:appended|acrescent|adicion)',
        content,
    ):
        errors.append(
            f'{file_path}:1: B3 API documentation must explain automatic '
            'extension when .parquet is omitted'
        )

    return errors


def _check_b3_catalog_semantics(file_path: Path, content: str) -> list[str]:
    """Require validated duplicate equivalence and explicit empty coverage."""
    paragraphs = [text for _, text in _normalized_paragraphs(content)]
    errors: list[str] = []
    equivalent_inputs = any(
        re.search(
            r'(?i)ZIP.{0,200}(?:only|somente).{0,100}(?:identical|idêntic)',
            paragraph,
        )
        and re.search(
            r'(?i)(?:both|ambos).{0,100}(?:validat|validad)', paragraph
        )
        for paragraph in paragraphs
    )
    if not equivalent_inputs:
        errors.append(
            f'{file_path}:1: B3 API docs must require full validation of '
            'both ZIP/TXT inputs and identical contents before selecting ZIP'
        )
    empty_coverage = any(
        re.search(r'(?i)empty\s+directory|diretório\s+vazio', paragraph)
        and 'missing_years' in paragraph
        and 'zero' in paragraph.casefold()
        and re.search(r'(?i)success\s*=\s*false', paragraph)
        for paragraph in paragraphs
    )
    filtered_empty = any(
        re.search(
            r'(?i)sources?.{0,80}valid|valid.{0,80}sources?|'
            r'fontes.{0,80}válid',
            paragraph,
        )
        and re.search(r'(?i)success\s*=\s*true', paragraph)
        for paragraph in paragraphs
    )
    if (
        not empty_coverage
        or not filtered_empty
        or 'EmptyDirectoryError' in content
    ):
        errors.append(
            f'{file_path}:1: B3 API docs must distinguish missing-year '
            'failure with zero resolved files from valid filtered empty output'
        )
    return errors


def check_public_b3_signature_contract(
    file_path: Path,
    code_blocks: list[tuple[int, str, str]],
    contracts: SourceContracts,
) -> list[str]:
    """Compare the documented B3 extraction signature to source."""
    if not is_public_b3_api_document(file_path):
        return []

    return compare_documented_extract_signature(
        file_path, code_blocks, contracts
    )


def check_public_cvm_api_contract(
    file_path: Path,
    content: str,
    contracts: SourceContracts,
) -> list[str]:
    """Validate CVM result, year, and exception names against source."""
    if not is_public_cvm_api_document(file_path):
        return []

    errors = _missing_markers(
        file_path,
        content,
        (
            *contracts.download_result_fields,
            *contracts.download_result_properties,
        ),
        'DownloadResultCVM',
    )
    errors.extend(
        _missing_markers(
            file_path,
            content,
            contracts.available_years_attributes,
            'AvailableYearsInfoCVM',
        )
    )

    candidates = set(
        re.findall(
            r'`([A-Z][A-Za-z0-9]*(?:Error|Exception)|Invalid[A-Z][A-Za-z0-9]*)`',
            content,
        )
    )
    for candidate in sorted(candidates - contracts.exception_names):
        errors.append(
            f'{file_path}:1: documented CVM exception does not exist: '
            f'{candidate}'
        )
    return errors
