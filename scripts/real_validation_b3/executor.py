"""Execute annual and parity COTAHIST validation cases."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import input_validation
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from globaldatafinance.macro_exceptions import ExtractionError

from ..cotahist_oracle import OracleMismatch, reconcile_sources
from ..real_validation_types import ValidationCase
from ..real_validation_utils import emit_progress, failed_details
from .artifact_validation import (
    _BATCH_SIZE,
    _failed_validation,
    _passed_details,
    _validate_result,
)
from .frozen_baseline import (
    _case_source_paths,
    _expected_frozen_checksums,
    _ordered_rows_sha256,
    _validate_frozen_baseline,
)


def execute_cotahist_case(
    case: ValidationCase, workspace: Path
) -> dict[str, Any]:
    """Run an annual or multi-year case with explicit historical acceptance."""
    input_path = Path(case.input_path)
    source_paths = _case_source_paths(case)
    try:
        for path in source_paths:
            input_validation.validate_cotahist_input(path)
    except (CotahistCatalogError, ExtractionError, OSError) as error:
        return failed_details(
            None, f'COTAHIST input validation failed: {error}'
        )

    if case.mode == 'multi_parity':
        return _execute_multi_year_parity(case, source_paths, workspace)
    if case.mode == 'parity':
        return _execute_parity(case, input_path, workspace)
    result, details = _execute_mode(
        input_path, case.year, 'fast', workspace / 'fast'
    )
    if not details['valid']:
        return _failed_validation(result, details)
    return _passed_details(result, details, 'COTAHIST fast extraction passed')


def _execute_mode(
    input_path: Path,
    year: int,
    mode: str,
    output_directory: Path,
    *,
    source_paths: Sequence[Path] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    frozen_baseline: bool = False,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Run one public extraction and independently reconcile every row."""
    output_directory.mkdir(parents=True, exist_ok=True)
    first = year if initial_year is None else initial_year
    last = year if last_year is None else last_year
    emit_progress(f'{mode}: extracting {first}..{last}')
    result: Mapping[str, Any] = asyncio.run(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(input_path.parent),
            assets_list=['todos'],
            initial_year=first,
            last_year=last,
            destination_path=str(output_directory),
            output_filename='cotahist',
            processing_mode=mode,
            verbose=False,
        )
    )
    emit_progress(f'{mode}: validating the published Parquet')
    structural = _validate_result(result, output_directory, first, last)
    if not structural['valid']:
        return result, structural
    selected_sources = tuple(source_paths or (input_path,))
    expected_checksums = _expected_frozen_checksums(
        selected_sources, enabled=frozen_baseline
    )
    try:
        emit_progress(f'{mode}: reconciling every raw quotation with Parquet')
        reconciliation = reconcile_sources(
            selected_sources,
            Path(str(result['output_file'])),
            public_result=dict(result),
            expected_checksums=expected_checksums,
            batch_size=_BATCH_SIZE,
        )
        if expected_checksums is not None:
            _validate_frozen_baseline(reconciliation)
    except (OracleMismatch, OSError, RuntimeError, ValueError) as error:
        return result, {
            'valid': False,
            'message': f'independent raw reconciliation failed: {error}',
        }
    structural.update(
        {
            'raw_reconciliation': reconciliation,
            'ordered_rows_sha256': _ordered_rows_sha256(
                Path(str(result['output_file']))
            ),
        }
    )
    emit_progress(
        f'{mode}: reconciliation passed; rows={structural["record_count"]}'
    )
    return result, structural


def _execute_parity(
    case: ValidationCase, input_path: Path, workspace: Path
) -> dict[str, Any]:
    """Reconcile both annual modes and compare their complete row order."""
    fast_result, fast_details = _execute_mode(
        input_path, case.year, 'fast', workspace / 'fast'
    )
    slow_result, slow_details = _execute_mode(
        input_path, case.year, 'slow', workspace / 'slow'
    )
    return _parity_result(fast_result, fast_details, slow_result, slow_details)


def _execute_multi_year_parity(
    case: ValidationCase,
    source_paths: Sequence[Path],
    workspace: Path,
) -> dict[str, Any]:
    """Reconcile the full requested range in fast and slow mode."""
    if (
        not case.input_files
        or case.initial_year is None
        or case.last_year is None
    ):
        return failed_details(None, 'multi-year COTAHIST case lacks its range')
    anchor = source_paths[0]
    fast_result, fast_details = _execute_mode(
        anchor,
        case.initial_year,
        'fast',
        workspace / 'fast',
        source_paths=source_paths,
        initial_year=case.initial_year,
        last_year=case.last_year,
        frozen_baseline=case.frozen_baseline,
    )
    slow_result, slow_details = _execute_mode(
        anchor,
        case.initial_year,
        'slow',
        workspace / 'slow',
        source_paths=source_paths,
        initial_year=case.initial_year,
        last_year=case.last_year,
        frozen_baseline=case.frozen_baseline,
    )
    return _parity_result(fast_result, fast_details, slow_result, slow_details)


def _parity_result(
    fast_result: Mapping[str, Any],
    fast_details: Mapping[str, Any],
    slow_result: Mapping[str, Any],
    slow_details: Mapping[str, Any],
) -> dict[str, Any]:
    public_result = {'fast': dict(fast_result), 'slow': dict(slow_result)}
    if not fast_details.get('valid'):
        return _failed_validation(public_result, fast_details)
    if not slow_details.get('valid'):
        return _failed_validation(public_result, slow_details)
    compared_keys = (
        'record_count',
        'schema',
        'date_range',
        'ordered_rows_sha256',
    )
    for key in compared_keys:
        if fast_details.get(key) != slow_details.get(key):
            return failed_details(public_result, f'fast/slow {key} mismatch')
    artifacts = [
        *[dict(item, mode='fast') for item in fast_details['artifacts']],
        *[dict(item, mode='slow') for item in slow_details['artifacts']],
    ]
    reconciliation = dict(fast_details['raw_reconciliation'])
    reconciliation['slowOutputSha256'] = slow_details['raw_reconciliation'][
        'outputSha256'
    ]
    return {
        'status': 'passed',
        'message': 'COTAHIST fast/slow exact ordered parity passed',
        'publicResult': public_result,
        'published': True,
        'artifactCount': len(artifacts),
        'artifacts': artifacts,
        'recordCount': fast_details['record_count'],
        'schema': fast_details['schema'],
        'dateRange': fast_details['date_range'],
        'rawReconciliation': reconciliation,
        'orderedRowsSha256': fast_details['ordered_rows_sha256'],
        'comparisonMethod': 'independent ordered raw-to-Parquet equality',
        'modeParity': 'exact ordered rows',
    }
