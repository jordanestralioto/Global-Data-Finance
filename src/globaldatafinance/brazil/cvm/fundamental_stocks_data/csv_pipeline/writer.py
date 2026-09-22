"""Streaming Arrow Parquet writing and validation for CVM CSV members."""

from __future__ import annotations

import errno
import hashlib
from contextlib import suppress
from pathlib import Path
from typing import Any, NoReturn

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .....macro_exceptions import (
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)
from .constants import FALSE_VALUES, NULL_TOKENS, ROW_GROUP_SIZE, TRUE_VALUES
from .models import CsvAnalysis, CsvPipelineResult, EncodingPlan
from .source import ReopenableCsvSource, binary_source


def write_parquet(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
    staged_path: Path,
    analysis: CsvAnalysis,
    schema: pa.Schema,
) -> CsvPipelineResult:
    """Write, close, and reopen one staged Parquet with fixed row groups."""
    try:
        staged_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        _raise_staged_write_error(staged_path, error)
    rows_written = 0
    row_groups: list[int] = []
    writer = None
    try:
        writer = pq.ParquetWriter(
            staged_path,
            schema,
            compression='zstd',
            compression_level=3,
        )
        if analysis.rows:
            rows_written, row_groups = _write_arrow_batches(
                source, utf8_source, plan, writer, schema, staged_path
            )
        writer.close()
        writer = None
    except pa.ArrowException as error:
        raise ExtractionError(
            str(source.source_path),
            f'Could not convert CSV member through Arrow: {error}',
        ) from error
    except (ExtractionError, DiskFullError, ParquetWriteError):
        raise
    except OSError as error:
        _raise_staged_write_error(staged_path, error)
    finally:
        if writer is not None:
            with suppress(OSError):
                writer.close()
    if rows_written != analysis.rows:
        raise ExtractionError(
            str(source.source_path),
            f'CSV row count mismatch: expected {analysis.rows}, '
            f'wrote {rows_written}',
        )
    validate_parquet(source, staged_path, schema, rows_written, row_groups)
    fingerprint = hashlib.sha256(
        schema.to_string().encode('utf-8')
    ).hexdigest()
    return CsvPipelineResult(
        rows=rows_written,
        schema_fingerprint=fingerprint,
        schema=schema,
        header=analysis.header,
        row_groups=tuple(row_groups),
    )


def _write_arrow_batches(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
    writer: Any,
    schema: pa.Schema,
    output_path: Path,
) -> tuple[int, list[int]]:
    """Stream explicitly typed Arrow CSV batches into fixed row groups."""
    rows_written = 0
    row_groups: list[int] = []
    pending_batches: list[Any] = []
    pending_rows = 0
    try:
        with binary_source(source, utf8_source, plan) as opened:
            reader = pacsv.open_csv(
                opened,
                read_options=pacsv.ReadOptions(
                    block_size=256 * 1024,
                    use_threads=False,
                ),
                parse_options=pacsv.ParseOptions(
                    delimiter=';',
                    quote_char=False,
                    newlines_in_values=False,
                    ignore_empty_lines=False,
                ),
                convert_options=pacsv.ConvertOptions(
                    column_types=schema,
                    null_values=sorted(NULL_TOKENS),
                    strings_can_be_null=True,
                    quoted_strings_can_be_null=True,
                    true_values=TRUE_VALUES,
                    false_values=FALSE_VALUES,
                ),
            )
            for batch in reader:
                offset = 0
                while offset < batch.num_rows:
                    size = min(
                        ROW_GROUP_SIZE - pending_rows,
                        batch.num_rows - offset,
                    )
                    pending_batches.append(batch.slice(offset, size))
                    pending_rows += size
                    offset += size
                    if pending_rows == ROW_GROUP_SIZE:
                        _write_row_group(
                            writer, pending_batches, schema, output_path
                        )
                        rows_written += pending_rows
                        row_groups.append(pending_rows)
                        pending_batches.clear()
                        pending_rows = 0
            if pending_rows:
                _write_row_group(writer, pending_batches, schema, output_path)
                rows_written += pending_rows
                row_groups.append(pending_rows)
    except (ExtractionError, ParquetWriteError):
        raise
    except OSError as error:
        raise ExtractionError(
            str(source.source_path),
            f'Could not read CSV member through Arrow: {error}',
        ) from error
    return rows_written, row_groups


def _write_row_group(
    writer: Any,
    batches: list[Any],
    schema: pa.Schema,
    output_path: Path,
) -> None:
    """Write one bounded group without constructing Python arrays."""
    table = pa.Table.from_batches(batches, schema=schema)
    try:
        writer.write_table(table, row_group_size=ROW_GROUP_SIZE)
    except OSError as error:
        _raise_staged_write_error(output_path, error)


def validate_parquet(
    source: ReopenableCsvSource,
    path: Path,
    schema: pa.Schema,
    rows: int,
    row_groups: list[int],
) -> None:
    """Verify schema, metadata, rows, and row groups before publication."""
    try:
        parquet = pq.ParquetFile(path)
    except pa.ArrowException as error:
        raise ExtractionError(
            str(source.source_path),
            f'Could not reopen staged Parquet: {error}',
        ) from error
    except OSError as error:
        _raise_staged_write_error(path, error)
    metadata = parquet.metadata
    if metadata is None or metadata.num_rows != rows:
        raise ExtractionError(
            str(source.source_path),
            'Staged Parquet row count validation failed',
        )
    if parquet.schema_arrow != schema:
        raise ExtractionError(
            str(source.source_path),
            'Staged Parquet schema validation failed',
        )
    metadata_map = parquet.schema_arrow.metadata
    if metadata_map and b'pandas' in metadata_map:
        raise ExtractionError(
            str(source.source_path),
            'Staged Parquet unexpectedly contains pandas metadata',
        )
    observed = [
        metadata.row_group(index).num_rows
        for index in range(metadata.num_row_groups)
    ]
    if observed != row_groups or sum(observed) != rows:
        raise ExtractionError(
            str(source.source_path),
            'Staged Parquet row group validation failed',
        )


def _raise_staged_write_error(path: Path, error: OSError) -> NoReturn:
    """Translate filesystem failures for one staged Parquet artifact."""
    if error.errno == errno.ENOSPC:
        raise DiskFullError(str(path)) from error
    raise ParquetWriteError(str(path), str(error)) from error
