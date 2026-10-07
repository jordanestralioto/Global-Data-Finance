"""Build deterministic real-validation cases for each data source."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    index_cotahist_catalog,
    select_cotahist_file,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)

from ..real_validation_b3.frozen_baseline import expected_frozen_checksums
from ..real_validation_types import ValidationCase, ValidationInputSnapshot
from ..real_validation_utils import sha256_file

Source = Literal['cotahist', 'cvm', 'all']

COTAHIST_START = 1986

COTAHIST_END = date.today().year

CVM_START = 2010

CVM_END = 2026

CVM_DOCUMENT_WINDOWS: dict[str, tuple[int, int]] = {
    'CGVN': (2018, 2026),
    'FRE': (2010, 2026),
    'FCA': (2010, 2026),
    'DFP': (2010, 2026),
    'ITR': (2011, 2026),
    'IPE': (2010, 2026),
    'VLMO': (2018, 2026),
}

_CVM_DOCUMENT_ORDER = tuple(CVM_DOCUMENT_WINDOWS)


def build_cases(
    *,
    source: Source,
    initial_year: int | None,
    last_year: int | None,
    document: str | None,
    cotahist_path: str | None,
    cvm_output: str | None,
    cotahist_modes: Literal['fast', 'parity', 'all'] = 'all',
    cotahist_frozen_baseline: bool = False,
) -> list[ValidationCase]:
    """Build a stable case matrix without reading environment variables."""
    cases: list[ValidationCase] = []
    if cotahist_frozen_baseline and (
        source == 'cvm' or cotahist_modes != 'all'
    ):
        raise ValueError(
            '--cotahist-frozen-baseline requires COTAHIST and '
            '--cotahist-mode all'
        )
    if source in {'cotahist', 'all'}:
        cases.extend(
            _build_cotahist_cases(
                cotahist_path,
                initial_year,
                last_year,
                cotahist_modes,
                cotahist_frozen_baseline,
            )
        )
    if source in {'cvm', 'all'}:
        cases.extend(
            _build_cvm_cases(
                cvm_output,
                initial_year,
                last_year,
                document,
            )
        )
    return sorted(cases, key=lambda case: case.case_id)


def canonical_cvm_case(
    case: ValidationCase, expected_output_root: str
) -> ValidationCase:
    """Rebuild and validate one CVM case from the official matrix.

    A persisted campaign manifest is evidence, not authority for a network
    endpoint.  Resume and worker paths use this helper before any CVM request
    so every identity field and the endpoint are derived from code-owned
    document/year rules.

    Args:
        case: CVM case decoded from a manifest or supplied to a worker.
        expected_output_root: Validated campaign destination that owns the
            CVM output for this case.

    Returns:
        The reconstructed official CVM case.

    Raises:
        ValueError: If ``case`` cannot be represented by the official matrix.
    """
    if case.source != 'cvm':
        raise ValueError('only CVM cases can be reconstructed')
    if case.document is None:
        raise ValueError('CVM case document is required')

    expected_cases = _build_cvm_cases(
        expected_output_root,
        case.year,
        case.year,
        case.document,
    )
    if len(expected_cases) != 1:
        raise ValueError(
            'CVM case is outside the official document/year matrix'
        )

    expected = expected_cases[0]
    mismatches = _cvm_case_mismatches(case, expected)
    if mismatches:
        raise ValueError(
            'CVM case does not match the official matrix: '
            + ', '.join(mismatches)
        )
    return expected


def _build_cotahist_cases(
    raw_path: str | None,
    initial_year: int | None,
    last_year: int | None,
    modes: Literal['fast', 'parity', 'all'],
    frozen_baseline: bool = False,
) -> list[ValidationCase]:
    if not raw_path:
        raise ValueError('--cotahist-path is required for COTAHIST cases')
    if initial_year is None or last_year is None:
        discovered = index_cotahist_catalog(raw_path)
        if not discovered:
            raise CotahistCatalogError(
                'COTAHIST catalog contains no annual source files'
            )
        start = min(discovered) if initial_year is None else initial_year
        end = max(discovered) if last_year is None else last_year
    else:
        start, end = initial_year, last_year
        discovered = {}
    if start < COTAHIST_START or end > COTAHIST_END or start > end:
        raise ValueError(
            f'COTAHIST years must be within {COTAHIST_START}..{COTAHIST_END}'
        )
    selected_years = tuple(range(start, end + 1))
    catalog = discovered or index_cotahist_catalog(
        raw_path, expected_years=selected_years
    )
    missing = set(selected_years) - set(catalog)
    if missing:
        raise CotahistCatalogError(
            f'COTAHIST catalog is missing selected years: {sorted(missing)}'
        )
    selected_by_year = {
        year: select_cotahist_file(catalog, year) for year in selected_years
    }
    expected_frozen_checksums(
        tuple(selected_by_year.values()), enabled=frozen_baseline
    )
    snapshots = tuple(
        ValidationInputSnapshot(
            path=str(path.resolve()),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in selected_by_year.values()
    )
    cases: list[ValidationCase] = []
    snapshot_by_year = dict(zip(selected_by_year, snapshots, strict=True))
    for year, path in selected_by_year.items():
        snapshot = snapshot_by_year[year]
        if modes in {'fast', 'all'}:
            cases.append(
                ValidationCase(
                    case_id=f'cotahist-fast-{year}',
                    source='cotahist',
                    year=year,
                    input_path=str(path),
                    output_root='',
                    mode='fast',
                    input_size_bytes=snapshot.size_bytes,
                    input_sha256=snapshot.sha256,
                    initial_year=year,
                    last_year=year,
                    input_files=(snapshot,),
                )
            )
        if modes in {'parity', 'all'}:
            cases.append(
                ValidationCase(
                    case_id=f'cotahist-parity-{year}',
                    source='cotahist',
                    year=year,
                    input_path=str(path),
                    output_root='',
                    mode='parity',
                    input_size_bytes=snapshot.size_bytes,
                    input_sha256=snapshot.sha256,
                    initial_year=year,
                    last_year=year,
                    input_files=(snapshot,),
                )
            )
    if modes == 'all':
        first_path = selected_by_year[start]
        first_snapshot = snapshot_by_year[start]
        cases.append(
            ValidationCase(
                case_id=f'cotahist-multi-parity-{start}-{end}',
                source='cotahist',
                year=start,
                input_path=str(first_path.resolve()),
                output_root='',
                mode='multi_parity',
                input_size_bytes=first_snapshot.size_bytes,
                input_sha256=first_snapshot.sha256,
                initial_year=start,
                last_year=end,
                input_files=snapshots,
                frozen_baseline=frozen_baseline,
            )
        )
    return cases


def _build_cvm_cases(
    raw_output: str | None,
    initial_year: int | None,
    last_year: int | None,
    document: str | None,
) -> list[ValidationCase]:
    if not raw_output:
        raise ValueError('--cvm-output is required for CVM cases')
    output_root = normalized_path(raw_output)
    if output_root is None:
        raise ValueError('--cvm-output is required for CVM cases')
    start = CVM_START if initial_year is None else initial_year
    end = CVM_END if last_year is None else last_year
    if start < CVM_START or end > CVM_END or start > end:
        raise ValueError('CVM years must be within 2010..2026')
    cases: list[ValidationCase] = []
    for item in selected_documents(document):
        first_valid, last_valid = CVM_DOCUMENT_WINDOWS[item]
        for year in range(max(start, first_valid), min(end, last_valid) + 1):
            url = (
                'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/'
                f'{item}/DADOS/{item.lower()}_cia_aberta_{year}.zip'
            )
            cases.append(
                ValidationCase(
                    case_id=f'cvm-{item}-{year}',
                    source='cvm',
                    year=year,
                    input_path=url,
                    output_root=output_root,
                    document=item,
                    mode='cvm',
                    url=url,
                )
            )
    return cases


def _cvm_case_mismatches(
    actual: ValidationCase, expected: ValidationCase
) -> list[str]:
    """Return the persisted CVM fields that differ from the official case."""
    fields = (
        ('caseId', actual.case_id, expected.case_id),
        ('source', actual.source, expected.source),
        ('document', actual.document, expected.document),
        ('year', actual.year, expected.year),
        ('mode', actual.mode, expected.mode),
        ('inputPath', actual.input_path, expected.input_path),
        ('outputRoot', actual.output_root, expected.output_root),
        ('url', actual.url, expected.url),
        ('inputSizeBytes', actual.input_size_bytes, expected.input_size_bytes),
        ('inputSha256', actual.input_sha256, expected.input_sha256),
        ('initialYear', actual.initial_year, expected.initial_year),
        ('lastYear', actual.last_year, expected.last_year),
        ('inputFiles', actual.input_files, expected.input_files),
    )
    return [
        name
        for name, actual_value, expected_value in fields
        if actual_value != expected_value
    ]


def normalized_path(raw_path: str | None) -> str | None:
    """Return an absolute caller path without creating or inspecting it."""
    if raw_path is None:
        return None
    return str(Path(raw_path).expanduser().resolve())


def selected_documents(document: str | None) -> tuple[str, ...]:
    """Resolve the requested CVM document selection in canonical order."""
    if document is None or document.casefold() == 'all':
        return _CVM_DOCUMENT_ORDER
    normalized = document.strip().upper()
    if normalized not in CVM_DOCUMENT_WINDOWS:
        available = ', '.join(_CVM_DOCUMENT_ORDER)
        raise ValueError(
            f'unsupported CVM document {document!r}; available: {available}'
        )
    return (normalized,)
