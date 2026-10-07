"""Validate public B3 results and their Parquet artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from ..cotahist_oracle import independent_schema
from ..real_validation_utils import (
    failed_details,
    sha256_file,
    temporary_paths,
)

B3_SCHEMA = {field.name: str(field.type) for field in independent_schema()}

BATCH_SIZE = 8_192


def validate_result(
    result: Mapping[str, Any],
    output_directory: Path,
    initial_year: int,
    last_year: int,
) -> dict[str, Any]:
    """Check public facts and artifact structure before raw reconciliation."""
    if not _public_result_is_successful(result):
        return _public_failure(result)
    output_directory = output_directory.resolve()
    output_path = Path(str(result['output_file'])).resolve()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return {
            'valid': False,
            'message': 'B3 Parquet output is missing or empty',
        }
    if output_path.parent != output_directory.resolve():
        return {'valid': False, 'message': 'B3 output escaped its directory'}
    if sorted(output_directory.glob('*.parquet')) != [output_path]:
        return {'valid': False, 'message': 'B3 output file count is not one'}
    schema_error = validate_schema(output_path)
    if schema_error:
        return {'valid': False, 'message': schema_error}
    metadata_error = validate_metadata(output_path)
    if metadata_error:
        return {'valid': False, 'message': metadata_error}
    leftovers = temporary_paths(output_directory)
    if leftovers:
        return {
            'valid': False,
            'message': f'B3 temporary files leaked: {leftovers}',
        }
    try:
        frame = _validate_frame(output_path, result, initial_year, last_year)
    except (OSError, RuntimeError, ValueError, TypeError) as error:
        return {
            'valid': False,
            'message': f'B3 artifact validation failed: {error}',
        }
    if frame['error']:
        return {'valid': False, 'message': str(frame['error'])}
    return {
        'valid': True,
        'message': '',
        'record_count': int(result['total_records']),
        'schema': B3_SCHEMA,
        'date_range': frame['date_range'],
        'artifacts': [
            {
                'path': output_path.name,
                'sizeBytes': output_path.stat().st_size,
                'rows': int(result['total_records']),
                'sha256': sha256_file(output_path),
                'pyarrowReadable': True,
                'metadataPresent': True,
            }
        ],
    }


def _public_failure(result: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve typed public diagnostics and classify storage prerequisites."""
    errors = result.get('errors', {})
    messages = (
        [str(value) for value in errors.values()]
        if isinstance(errors, Mapping)
        else []
    )
    external = any(
        message.startswith(('DiskFullError:', 'PathPermissionError:'))
        for message in messages
    )
    message = 'public B3 result is unsuccessful'
    if messages:
        message += ': ' + '; '.join(messages)
    return {
        'valid': False,
        'message': message,
        'failure_status': 'external_failure' if external else 'failed',
    }


def failed_validation(
    result: Mapping[str, Any], details: Mapping[str, Any]
) -> dict[str, Any]:
    """Carry validation failure classification into campaign evidence."""
    failure = failed_details(result, str(details['message']))
    if details.get('failure_status') == 'external_failure':
        failure['status'] = 'external_failure'
    return failure


def _public_result_is_successful(result: Mapping[str, Any]) -> bool:
    integrity = result.get('integrity')
    return (
        result.get('success') is True
        and result.get('schema_version') == 2
        and result.get('error_count') == 0
        and result.get('errors') == {}
        and isinstance(result.get('output_file'), str)
        and bool(result.get('output_file'))
        and isinstance(integrity, dict)
        and integrity.get('status') == 'passed'
        and integrity.get('selection_complete') is True
        and integrity.get('source_complete') is True
        and integrity.get('missing_years') == []
    )


def _validate_frame(
    output_path: Path,
    result: Mapping[str, Any],
    initial_year: int,
    last_year: int,
) -> dict[str, Any]:
    parquet = pq.ParquetFile(output_path)
    row_count = 0
    first_date = None
    last_date = None
    for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
        dates = batch.column('data_pregao').to_pylist()
        markets = batch.column('tipo_mercado').to_pylist()
        if not dates or not markets:
            continue
        row_count += batch.num_rows
        batch_first = min(dates)
        batch_last = max(dates)
        first_date = (
            batch_first if first_date is None else min(first_date, batch_first)
        )
        last_date = (
            batch_last if last_date is None else max(last_date, batch_last)
        )
        if any(
            not isinstance(code, str)
            or len(code) != 3
            or not code.isascii()
            or not code.isdecimal()
            for code in markets
        ):
            return {
                'error': 'output contains an invalid TPMERC',
                'date_range': None,
            }
    if row_count != result['total_records']:
        return {'error': 'B3 row count mismatch', 'date_range': None}
    if first_date is None or last_date is None:
        return {'error': 'B3 date range is empty', 'date_range': None}
    if first_date.year < initial_year or last_date.year > last_year:
        return {
            'error': 'B3 dates fall outside requested years',
            'date_range': None,
        }
    return {
        'error': None,
        'date_range': (first_date.isoformat(), last_date.isoformat()),
    }


def validate_schema(output_path: Path) -> str | None:
    """Compare persisted fields with the independent B3 v2 schema."""
    parquet = pq.ParquetFile(output_path)
    actual = [
        (field.name, str(field.type), field.nullable)
        for field in parquet.schema_arrow
    ]
    expected_schema = independent_schema()
    expected = [
        (field.name, str(field.type), field.nullable)
        for field in expected_schema
    ]
    return None if actual == expected else 'B3 schema differs from v2 oracle'


def validate_metadata(output_path: Path) -> str | None:
    """Check the schema version and integrity manifest metadata."""
    metadata = pq.ParquetFile(output_path).schema_arrow.metadata or {}
    if metadata.get(b'globaldatafinance.b3.schema_version') != b'2':
        return 'B3 schema version metadata is invalid'
    if b'globaldatafinance.b3.integrity_manifest' not in metadata:
        return 'B3 integrity footer manifest is missing'
    return None


def passed_details(
    result: Mapping[str, Any], details: Mapping[str, Any], message: str
) -> dict[str, Any]:
    """Build successful validation evidence from reconciled artifacts."""
    reconciliation = dict(details['raw_reconciliation'])
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
        'rawReconciliation': reconciliation,
        'orderedRowsSha256': details['ordered_rows_sha256'],
        'comparisonMethod': 'independent ordered raw-to-Parquet equality',
    }
