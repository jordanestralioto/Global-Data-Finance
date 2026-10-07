"""Bounded full-file readback verification for B3 Parquet outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....macro_exceptions import ExtractionError
from ..async_execution import check_phase_cancellation
from ..models import ValidatedCotahistSource
from ..row_digest import B3OrderedRowDigest
from .metadata_verification import open_verified_parquet, verify_row_count
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
    expected_coordinates: dict[str, object] = field(default_factory=dict)


def verify_b3_parquet(
    path: Path,
    *,
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
    manifest_sources: tuple[ValidatedCotahistSource, ...] | None = None,
) -> B3ParquetReadback:
    """Read every row and prove schema, provenance, and source order."""
    parquet, actual_schema = open_verified_parquet(
        path, expected_schema, sources, manifest_sources
    )
    try:
        return _read_open_parquet(path, parquet, actual_schema, sources)
    finally:
        parquet.close()


def verify_b3_parquet_metadata(
    path: Path,
    *,
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
    manifest_sources: tuple[ValidatedCotahistSource, ...] | None = None,
) -> int:
    """Prove schema, footer manifest, and row count without reading rows.

    This is the metadata half of ``verify_b3_parquet``. It does not establish
    values, provenance, order, or digests; those require the full readback.
    """
    parquet, _ = open_verified_parquet(
        path, expected_schema, sources, manifest_sources
    )
    try:
        return verify_row_count(path, parquet, sources)
    finally:
        parquet.close()


def _read_open_parquet(
    path: Path,
    parquet: Any,
    actual_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
) -> B3ParquetReadback:
    expected_rows = verify_row_count(path, parquet, sources)
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
        columns = canonical_columns(batch)
        coordinates = {
            name: batch.column(index).to_pylist()
            for name, index in field_indices.items()
        }
        offset = 0
        while offset < batch.num_rows:
            _finish_complete_sources(path, sources, state)
            if state.source_index >= len(sources):
                raise ExtractionError(
                    str(path), 'B3 Parquet contains rows beyond source bounds'
                )
            source = sources[state.source_index]
            length = min(
                batch.num_rows - offset,
                source.selected_quotes - state.source_rows,
            )
            for row_index in range(offset, offset + length):
                _record_readback_row(
                    path, row_index, coordinates, sources, state
                )
            state.source_digest.update_columns(
                [column.slice(offset, length) for column in columns]
            )
            offset += length
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
    row_index: int,
    coordinates: dict[str, list[Any]],
    sources: tuple[ValidatedCotahistSource, ...],
    state: _ReadbackState,
) -> None:
    source = sources[state.source_index]
    if not state.expected_coordinates:
        state.expected_coordinates = {
            'tipo_registro': '01',
            'id_fonte': source.content_sha256,
            'arquivo_origem': source.path.name,
            'membro_origem': source.member,
            'ano_origem': source.year,
        }
    _verify_source_coordinates(
        path, coordinates, row_index, source, state.expected_coordinates
    )
    trading_date = coordinates['data_pregao'][row_index]
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
    state.expected_coordinates = {}


def _verify_source_coordinates(
    path: Path,
    columns: dict[str, list[Any]],
    row_index: int,
    source: ValidatedCotahistSource,
    expected: dict[str, object],
) -> None:
    """Require each row to remain inside its preflighted source boundary."""
    for name, value in expected.items():
        actual = columns[name][row_index]
        if actual != value:
            raise ExtractionError(
                str(path),
                'B3 Parquet source boundary mismatch: '
                f'year={source.year}; field={name}; expected={value!r}; '
                f'observed={actual!r}',
            )
    physical_line = columns['linha_origem'][row_index]
    if not isinstance(physical_line, int) or physical_line < 1:
        raise ExtractionError(
            str(path),
            f'Invalid one-based COTAHIST line coordinate: {physical_line!r}',
        )
    original_record = columns['registro_original'][row_index]
    if not isinstance(original_record, bytes) or len(original_record) != 245:
        raise ExtractionError(
            str(path), 'B3 Parquet original quotation bytes are invalid'
        )
    trading_date = columns['data_pregao'][row_index]
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


def canonical_columns(batch: Any) -> list[Any]:
    """Convert each bounded Arrow column to its exact digest representation."""
    import pyarrow as pa
    import pyarrow.compute as pc

    columns = []
    for array in batch.columns:
        kind = array.type
        if (
            pa.types.is_date32(kind)
            or pa.types.is_decimal(kind)
            or pa.types.is_integer(kind)
        ):
            array = pc.cast(array, pa.large_string(), safe=True)
        elif not (
            pa.types.is_large_string(kind)
            or pa.types.is_fixed_size_binary(kind)
        ):
            raise ExtractionError(
                'B3 Parquet',
                f'Unsupported Arrow value type during digest readback: {kind}',
            )
        columns.append(array)
    return columns
