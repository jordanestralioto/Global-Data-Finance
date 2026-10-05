"""Bounded full-file readback verification for B3 Parquet outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....macro_exceptions import ExtractionError
from ..async_execution import check_phase_cancellation
from ..models import ValidatedCotahistSource
from ..row_digest import B3OrderedRowDigest
from .audit_metadata import (
    B3_AUDIT_METADATA_KEY,
    B3_SCHEMA_FINGERPRINT_METADATA_KEY,
    B3_SCHEMA_VERSION_METADATA_KEY,
)
from .schema import B3_SCHEMA_VERSION, schema_fingerprint
from .session import RECORD_BATCH_LIMIT

if TYPE_CHECKING:
    from pyarrow import Schema


@dataclass(frozen=True)
class B3ParquetReadback:
    """Facts independently observed while reading a closed Parquet file."""

    row_count: int
    first_trading_date: date | None
    last_trading_date: date | None
    source_digests: tuple[str, ...]
    source_row_counts: tuple[int, ...]


@dataclass
class _ReadbackState:
    source_index: int = 0
    source_rows: int = 0
    source_digest: B3OrderedRowDigest = field(
        default_factory=B3OrderedRowDigest
    )
    source_digests: list[str] = field(default_factory=list)
    source_row_counts: list[int] = field(default_factory=list)
    observed_rows: int = 0
    first_date: date | None = None
    last_date: date | None = None


def verify_b3_parquet(
    path: Path,
    *,
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
    manifest_sources: tuple[ValidatedCotahistSource, ...] | None = None,
) -> B3ParquetReadback:
    """Read every row and prove schema, provenance, and source order."""
    parquet, actual_schema = _validate_parquet_contract(
        path, expected_schema, sources, manifest_sources
    )
    try:
        return _read_open_parquet(path, parquet, actual_schema, sources)
    finally:
        parquet.close()


def _read_open_parquet(
    path: Path,
    parquet: Any,
    actual_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
) -> B3ParquetReadback:
    file_metadata = parquet.metadata
    expected_rows = sum(source.selected_quotes for source in sources)
    if file_metadata is None or file_metadata.num_rows != expected_rows:
        observed = None if file_metadata is None else file_metadata.num_rows
        raise ExtractionError(
            str(path),
            'B3 Parquet row count readback failed: '
            f'expected={expected_rows}; observed={observed}',
        )
    field_indices = {
        name: actual_schema.get_field_index(name)
        for name in (
            'data_pregao',
            'tipo_registro',
            'id_fonte',
            'arquivo_origem',
            'membro_origem',
            'ano_origem',
            'linha_origem',
            'registro_original',
        )
    }
    state = _verify_parquet_batches(
        path, parquet, actual_schema, field_indices, sources
    )
    if state.observed_rows != expected_rows:
        raise ExtractionError(
            str(path),
            'B3 Parquet observed row count changed during readback: '
            f'expected={expected_rows}; observed={state.observed_rows}',
        )
    return B3ParquetReadback(
        row_count=state.observed_rows,
        first_trading_date=state.first_date,
        last_trading_date=state.last_date,
        source_digests=tuple(state.source_digests),
        source_row_counts=tuple(state.source_row_counts),
    )


def _validate_parquet_contract(
    path: Path,
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
    manifest_sources: tuple[ValidatedCotahistSource, ...] | None,
) -> tuple[Any, Schema]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    try:
        actual_schema = parquet.schema_arrow
        if not actual_schema.remove_metadata().equals(
            expected_schema.remove_metadata(), check_metadata=True
        ):
            raise ExtractionError(
                str(path), 'B3 Parquet schema readback failed'
            )
        metadata = actual_schema.metadata or {}
        _verify_footer_metadata(
            metadata,
            expected_schema,
            sources if manifest_sources is None else manifest_sources,
        )
        if b'pandas' in metadata:
            raise ExtractionError(
                str(path), 'B3 Parquet unexpectedly contains pandas metadata'
            )
        return parquet, actual_schema
    except BaseException:
        parquet.close()
        raise


def _verify_parquet_batches(
    path: Path,
    parquet: Any,
    actual_schema: Schema,
    field_indices: dict[str, int],
    sources: tuple[ValidatedCotahistSource, ...],
) -> _ReadbackState:
    state = _ReadbackState()
    for batch in parquet.iter_batches(batch_size=RECORD_BATCH_LIMIT):
        check_phase_cancellation()
        _validate_batch(path, batch, actual_schema)
        columns = [
            batch.column(index).to_pylist()
            for index in range(batch.num_columns)
        ]
        for row_index in range(batch.num_rows):
            _record_readback_row(
                path, columns, row_index, field_indices, sources, state
            )
    _finish_remaining_sources(path, sources, state)
    return state


def _validate_batch(path: Path, batch: Any, actual_schema: Schema) -> None:
    if batch.schema != actual_schema:
        raise ExtractionError(str(path), 'B3 Parquet batch schema changed')
    for index, schema_field in enumerate(actual_schema):
        if not schema_field.nullable and batch.column(index).null_count:
            raise ExtractionError(
                str(path),
                'B3 Parquet required column contains nulls: '
                f'{schema_field.name}',
            )


def _record_readback_row(
    path: Path,
    columns: list[list[Any]],
    row_index: int,
    field_indices: dict[str, int],
    sources: tuple[ValidatedCotahistSource, ...],
    state: _ReadbackState,
) -> None:
    _finish_complete_sources(path, sources, state)
    if state.source_index >= len(sources):
        raise ExtractionError(
            str(path), 'B3 Parquet contains rows beyond source bounds'
        )
    row = [column[row_index] for column in columns]
    source = sources[state.source_index]
    _verify_source_coordinates(path, row, field_indices, source)
    state.source_digest.update(
        tuple(_canonical_arrow_value(value) for value in row)
    )
    trading_date = row[field_indices['data_pregao']]
    if not isinstance(trading_date, date):
        raise ExtractionError(
            str(path), 'B3 Parquet trading date has an invalid type'
        )
    state.first_date = (
        trading_date
        if state.first_date is None
        else min(state.first_date, trading_date)
    )
    state.last_date = (
        trading_date
        if state.last_date is None
        else max(state.last_date, trading_date)
    )
    state.source_rows += 1
    state.observed_rows += 1


def _finish_complete_sources(
    path: Path,
    sources: tuple[ValidatedCotahistSource, ...],
    state: _ReadbackState,
) -> None:
    while (
        state.source_index < len(sources)
        and state.source_rows == sources[state.source_index].selected_quotes
    ):
        _finish_source(path, sources[state.source_index], state)


def _finish_remaining_sources(
    path: Path,
    sources: tuple[ValidatedCotahistSource, ...],
    state: _ReadbackState,
) -> None:
    while state.source_index < len(sources):
        _finish_source(path, sources[state.source_index], state)


def _finish_source(
    path: Path,
    source: ValidatedCotahistSource,
    state: _ReadbackState,
) -> None:
    digest = state.source_digest.hexdigest()
    _finish_source_readback(path, source, state.source_rows, digest)
    state.source_row_counts.append(state.source_rows)
    state.source_digests.append(digest)
    state.source_index += 1
    state.source_rows = 0
    state.source_digest = B3OrderedRowDigest()


def _verify_footer_metadata(
    metadata: dict[bytes, bytes],
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
) -> None:
    """Validate the complete footer against the preflighted run manifest."""
    expected_fingerprint = schema_fingerprint(expected_schema)
    if metadata.get(B3_SCHEMA_VERSION_METADATA_KEY) != str(
        B3_SCHEMA_VERSION
    ).encode('ascii'):
        raise ExtractionError(
            'B3 Parquet', 'Schema version metadata is invalid'
        )
    if metadata.get(B3_SCHEMA_FINGERPRINT_METADATA_KEY) != (
        expected_fingerprint.encode('ascii')
    ):
        raise ExtractionError(
            'B3 Parquet', 'Logical schema fingerprint metadata is invalid'
        )
    raw_manifest = metadata.get(B3_AUDIT_METADATA_KEY)
    if raw_manifest is None:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is missing'
        )
    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is invalid'
        ) from error
    if not isinstance(manifest, dict):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is invalid'
        )
    if (
        manifest.get('schema_version') != B3_SCHEMA_VERSION
        or manifest.get('logical_schema_fingerprint') != expected_fingerprint
    ):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest schema is incompatible'
        )
    expected_digests = [
        {
            'year': source.year,
            'source': source.path.name,
            'rows_sha256': source.expected_rows_sha256,
        }
        for source in sources
    ]
    if manifest.get('ordered_content_digests') != expected_digests:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer ordered digests are incompatible'
        )
    if metadata != (expected_schema.metadata or {}):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer metadata differs from preflight'
        )


def _verify_source_coordinates(
    path: Path,
    row: list[object],
    field_indices: dict[str, int],
    source: ValidatedCotahistSource,
) -> None:
    """Require each row to remain inside its preflighted source boundary."""
    expected = {
        'tipo_registro': '01',
        'id_fonte': source.content_sha256,
        'arquivo_origem': source.path.name,
        'membro_origem': source.member,
        'ano_origem': source.year,
    }
    for name, value in expected.items():
        actual = row[field_indices[name]]
        if actual != value:
            raise ExtractionError(
                str(path),
                'B3 Parquet source boundary mismatch: '
                f'year={source.year}; field={name}; expected={value!r}; '
                f'observed={actual!r}',
            )
    physical_line = row[field_indices['linha_origem']]
    if not isinstance(physical_line, int) or physical_line < 1:
        raise ExtractionError(
            str(path),
            f'Invalid one-based COTAHIST line coordinate: {physical_line!r}',
        )
    original_record = row[field_indices['registro_original']]
    if not isinstance(original_record, bytes) or len(original_record) != 245:
        raise ExtractionError(
            str(path), 'B3 Parquet original quotation bytes are invalid'
        )
    trading_date = row[field_indices['data_pregao']]
    if not isinstance(trading_date, date) or trading_date.year != source.year:
        raise ExtractionError(
            str(path), 'B3 Parquet source trading year is invalid'
        )


def _finish_source_readback(
    path: Path,
    source: ValidatedCotahistSource,
    observed_rows: int,
    observed_digest: str,
) -> None:
    """Compare one contiguous output segment with preflight expectations."""
    if observed_rows != source.selected_quotes:
        raise ExtractionError(
            str(path),
            'B3 Parquet source segment row count mismatch: '
            f'source={source.path.name}; expected={source.selected_quotes}; '
            f'observed={observed_rows}',
        )
    if observed_digest != source.expected_rows_sha256:
        raise ExtractionError(
            str(path),
            'B3 Parquet source segment digest mismatch: '
            f'source={source.path.name}; expected='
            f'{source.expected_rows_sha256}; observed={observed_digest}',
        )


def _canonical_arrow_value(value: object) -> str | bytes | None:
    """Encode Arrow scalar values with the source parser's canonical forms."""
    if value is None or isinstance(value, (str, bytes)):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, int):
        return str(value)
    raise ExtractionError(
        'B3 Parquet',
        f'Unsupported Arrow value type during digest readback: '
        f'{type(value).__name__}',
    )
