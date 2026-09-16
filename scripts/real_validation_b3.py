"""Execute and validate one real COTAHIST case through the B3 facade."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    validate_cotahist_input,
)

from .real_validation_types import ValidationCase
from .real_validation_utils import failed_details, temporary_paths

B3_SCHEMA = {
    field.name: str(field.type) for field in parquet_writer.build_b3_schema()
}
_SORT_COLUMNS = list(B3_SCHEMA)
_FRAME_COMPARE_LIMIT = 256 * 1024 * 1024
_DIGEST_BATCH_SIZE = 100_000
_DIGEST_MODULUS = 1 << 256


def execute_cotahist_case(
    case: ValidationCase, workspace: Path
) -> dict[str, Any]:
    """Run fast or complete fast/slow parity for one annual archive."""
    input_path = Path(case.input_path)
    validate_cotahist_input(input_path)
    if case.mode == 'parity':
        return _execute_parity(case, input_path, workspace)
    result, details = _execute_mode(
        input_path, case.year, case.mode, workspace / 'fast'
    )
    if not details['valid']:
        return failed_details(result, details['message'])
    return _passed_details(result, details, 'COTAHIST fast extraction passed')


def _execute_mode(
    input_path: Path, year: int, mode: str, output_directory: Path
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    output_directory.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(input_path.parent),
            assets_list=['ações'],
            initial_year=year,
            last_year=year,
            destination_path=str(output_directory),
            output_filename='cotahist',
            processing_mode=mode,
            verbose=False,
        )
    )
    return result, _validate_result(result, output_directory, year)


def _execute_parity(
    case: ValidationCase, input_path: Path, workspace: Path
) -> dict[str, Any]:
    fast_result, fast_details = _execute_mode(
        input_path, case.year, 'fast', workspace / 'fast'
    )
    slow_result, slow_details = _execute_mode(
        input_path, case.year, 'slow', workspace / 'slow'
    )
    public_result = {'fast': fast_result, 'slow': slow_result}
    if not fast_details['valid']:
        return failed_details(public_result, fast_details['message'])
    if not slow_details['valid']:
        return failed_details(public_result, slow_details['message'])
    if fast_details['record_count'] != slow_details['record_count']:
        return failed_details(public_result, 'fast/slow row count mismatch')
    if fast_details['schema'] != slow_details['schema']:
        return failed_details(public_result, 'fast/slow schema mismatch')
    if fast_details['date_range'] != slow_details['date_range']:
        return failed_details(public_result, 'fast/slow date range mismatch')
    try:
        comparison_method = _compare_content(
            Path(fast_result['output_file']),
            Path(slow_result['output_file']),
        )
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        return failed_details(public_result, f'fast/slow mismatch: {error}')
    artifacts = [
        *[dict(item, mode='fast') for item in fast_details['artifacts']],
        *[dict(item, mode='slow') for item in slow_details['artifacts']],
    ]
    return {
        'status': 'passed',
        'message': (
            f'COTAHIST full fast/slow parity passed ({comparison_method})'
        ),
        'publicResult': public_result,
        'published': True,
        'artifactCount': len(artifacts),
        'artifacts': artifacts,
        'recordCount': fast_details['record_count'],
        'schema': fast_details['schema'],
        'dateRange': fast_details['date_range'],
        'comparisonMethod': comparison_method,
    }


def _validate_result(
    result: Mapping[str, Any], output_directory: Path, year: int
) -> dict[str, Any]:
    public_error = _validate_public_result(result)
    if public_error:
        return {'valid': False, 'message': public_error}
    output_path = Path(str(result['output_file']))
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return {
            'valid': False,
            'message': 'B3 Parquet output is missing or empty',
        }
    if output_path.parent != output_directory.resolve():
        return {'valid': False, 'message': 'B3 output escaped its directory'}
    parquet_files = sorted(output_directory.glob('*.parquet'))
    if parquet_files != [output_path]:
        return {'valid': False, 'message': 'B3 output file count is not one'}
    frame_error = _validate_frame(output_path, result, year)
    if frame_error:
        return {'valid': False, 'message': frame_error}
    metadata_error = _validate_metadata(output_path)
    if metadata_error:
        return {'valid': False, 'message': metadata_error}
    temporary = temporary_paths(output_directory)
    if temporary:
        return {
            'valid': False,
            'message': f'B3 temporary files leaked: {temporary}',
        }
    try:
        date_range = _date_range(output_path)
    except (OSError, RuntimeError, ValueError, TypeError) as error:
        return {
            'valid': False,
            'message': f'B3 date validation failed: {error}',
        }
    return {
        'valid': True,
        'message': '',
        'record_count': int(result['total_records']),
        'schema': {name: str(dtype) for name, dtype in B3_SCHEMA.items()},
        'date_range': date_range,
        'artifacts': [
            {
                'path': output_path.name,
                'sizeBytes': output_path.stat().st_size,
                'rows': int(result['total_records']),
                'pyarrowReadable': True,
                'metadataPresent': True,
            }
        ],
    }


def _validate_public_result(result: Mapping[str, Any]) -> str | None:
    """Validate the public B3 result counters before inspecting its file."""
    required = (
        result.get('success') is True,
        result.get('total_files') == 1,
        result.get('success_count') == 1,
        result.get('error_count') == 0,
        result.get('total_records', 0) > 0,
        result.get('errors') == {},
    )
    if not all(required):
        return 'public B3 result is unsuccessful'
    return None


def _validate_frame(
    output_path: Path, result: Mapping[str, Any], year: int
) -> str | None:
    """Validate schema, content counters, dates, tickers, and markets."""
    try:
        parquet = pq.ParquetFile(output_path)
        if parquet.schema_arrow != parquet_writer.build_b3_schema():
            return 'B3 schema mismatch'
        row_count = 0
        first_date = None
        last_date = None
        shortest_ticker: int | None = None
        markets = 0
        for batch in parquet.iter_batches(batch_size=_DIGEST_BATCH_SIZE):
            dates = batch.column('data_pregao').to_pylist()
            tickers = batch.column('ticker').to_pylist()
            market_codes = batch.column('tipo_mercado').to_pylist()
            row_count += batch.num_rows
            batch_first = min(dates)
            batch_last = max(dates)
            first_date = (
                batch_first
                if first_date is None
                else min(first_date, batch_first)
            )
            last_date = (
                batch_last if last_date is None else max(last_date, batch_last)
            )
            batch_ticker_length = min(len(str(ticker)) for ticker in tickers)
            shortest_ticker = (
                batch_ticker_length
                if shortest_ticker is None
                else min(shortest_ticker, batch_ticker_length)
            )
            markets += sum(code in {'010', '020'} for code in market_codes)
        if row_count != result['total_records']:
            return 'B3 row count mismatch'
        if first_date is None or last_date is None:
            return 'B3 date range is empty'
        if first_date.year != year or last_date.year != year:
            return 'B3 dates have wrong year'
        if shortest_ticker is None or shortest_ticker <= 0 or markets <= 0:
            return 'B3 ticker or market validation failed'
    except (OSError, RuntimeError, ValueError, TypeError) as error:
        return f'B3 artifact validation failed: {error}'
    return None


def _validate_metadata(output_path: Path) -> str | None:
    """Validate positive row metadata through PyArrow."""
    try:
        metadata = pq.ParquetFile(output_path).metadata
    except (OSError, RuntimeError, ValueError, TypeError) as error:
        return f'B3 Parquet metadata validation failed: {error}'
    if metadata is None or metadata.num_rows <= 0:
        return 'B3 Parquet metadata is invalid'
    return None


def _date_range(output_path: Path) -> tuple[str, str]:
    """Return the complete output date range in a report-safe form."""
    first_date = None
    last_date = None
    parquet = pq.ParquetFile(output_path)
    for batch in parquet.iter_batches(batch_size=_DIGEST_BATCH_SIZE):
        dates = batch.column('data_pregao').to_pylist()
        batch_first = min(dates)
        batch_last = max(dates)
        first_date = (
            batch_first if first_date is None else min(first_date, batch_first)
        )
        last_date = (
            batch_last if last_date is None else max(last_date, batch_last)
        )
    if first_date is None or last_date is None:
        raise ValueError('B3 date range is empty')
    return first_date.isoformat(), last_date.isoformat()


def _passed_details(
    result: Mapping[str, Any], details: Mapping[str, Any], message: str
) -> dict[str, Any]:
    return {
        'status': 'passed',
        'message': message,
        'publicResult': dict(result),
        'published': True,
        'artifactCount': len(details['artifacts']),
        'artifacts': details['artifacts'],
        'recordCount': details['record_count'],
        'schema': details['schema'],
        'dateRange': details['date_range'],
    }


def _compare_content(fast_path: Path, slow_path: Path) -> str:
    if max(fast_path.stat().st_size, slow_path.stat().st_size) <= (
        _FRAME_COMPARE_LIMIT
    ):
        if not _canonical_table(fast_path).equals(
            _canonical_table(slow_path), check_metadata=False
        ):
            raise AssertionError('canonical table mismatch')
        return 'full_frame'
    if _canonical_digest(fast_path) != _canonical_digest(slow_path):
        raise AssertionError('canonical content digest mismatch')
    return 'order_independent_batch_digest'


def _canonical_table(path: Path) -> Any:
    """Read and sort a bounded-size table for a full logical comparison."""
    table = pq.read_table(path)
    indices = pc.sort_indices(
        table,
        sort_keys=[(column, 'ascending') for column in _SORT_COLUMNS],
    )
    return table.take(indices)


def _canonical_digest(path: Path) -> str:
    """Hash all rows in bounded batches without depending on row order."""
    parquet = pq.ParquetFile(path)
    schema = '|'.join(
        f'{field.name}:{field.type}' for field in parquet.schema_arrow
    )
    row_count = 0
    xor_state = 0
    sum_state = 0
    square_state = 0
    for batch in parquet.iter_batches(batch_size=_DIGEST_BATCH_SIZE):
        for row in batch.to_pylist():
            encoded = json.dumps(
                row,
                default=str,
                ensure_ascii=True,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            row_value = int.from_bytes(hashlib.sha256(encoded).digest())
            xor_state ^= row_value
            sum_state = (sum_state + row_value) % _DIGEST_MODULUS
            square_state = (
                square_state + row_value * row_value
            ) % _DIGEST_MODULUS
            row_count += 1
    digest = hashlib.sha256()
    digest.update(schema.encode('utf-8'))
    digest.update(
        f'|{row_count}|{xor_state}|{sum_state}|{square_state}'.encode()
    )
    return digest.hexdigest()
