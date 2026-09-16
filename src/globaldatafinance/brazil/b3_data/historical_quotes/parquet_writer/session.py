"""Persistent bounded Arrow writer sessions for one B3 Parquet artifact."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from contextlib import suppress
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....macro_exceptions import ExtractionError
from .schema import B3_STRING_COLUMNS

if TYPE_CHECKING:
    from pyarrow import Schema

ROW_GROUP_LIMIT = 200_000
RECORD_BATCH_LIMIT = 25_000
_NULL_SENTINEL = '__GLOBALDATAFINANCE_NULL__'
_arrow: tuple[Any, Any, Any] | None = None


def _get_arrow() -> tuple[Any, Any, Any]:
    """Return cached (pyarrow, pyarrow.csv, pyarrow.parquet) modules."""
    global _arrow
    if _arrow is None:
        import pyarrow as pa
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        _arrow = (pa, pacsv, pq)
    return _arrow


class B3ParquetWriterSession:
    """Write one B3 artifact without rewriting prior row groups."""

    def __init__(self, row_group_limit: int = ROW_GROUP_LIMIT) -> None:
        """Initialize an unopened bounded session."""
        self.row_group_limit = row_group_limit
        self.path: Path | None = None
        self.schema: Schema | None = None
        self._writer: Any | None = None
        self._pending_batches: list[Any] = []
        self._pending_rows = 0
        self.rows_written = 0
        self._state = 'NEW'

    @property
    def state(self) -> str:
        """Return the lifecycle state of this writer session."""
        return self._state

    def open(self, path: Path, schema: Schema) -> B3ParquetWriterSession:
        """Open a writer with the fixed B3 physical Parquet configuration."""
        if self._state != 'NEW':
            raise RuntimeError(
                'B3 Parquet writer session can only be opened from NEW'
            )
        if self.row_group_limit <= 0:
            raise ValueError('row_group_limit must be positive')
        _, _, pq = _get_arrow()
        writer = None
        path_existed = path.exists()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = pq.ParquetWriter(
                path,
                schema,
                compression='zstd',
                compression_level=3,
                write_statistics=True,
                version='1.0',
                use_dictionary=list(B3_STRING_COLUMNS),
            )
        except Exception:
            if writer is not None:
                with suppress(Exception):
                    writer.close()
            self.path = None
            self.schema = None
            self._writer = None
            self._state = 'NEW'
            if not path_existed:
                with suppress(OSError):
                    path.unlink(missing_ok=True)
            raise
        self.path = path
        self.schema = schema
        self._writer = writer
        self._state = 'OPEN'
        return self

    def write_records(self, records: list[dict[str, object]]) -> None:
        """Convert bounded Python records and clear their buffer."""
        if self._writer is None or self.schema is None:
            raise RuntimeError('B3 Parquet writer session is not open')

        try:
            while records:
                size = min(len(records), RECORD_BATCH_LIMIT)
                chunk = records[:size]
                del records[:size]
                for batch in self._records_to_batches(chunk, self.schema):
                    self._pending_batches.append(batch)
                    self._pending_rows += batch.num_rows
                    if self._pending_rows >= self.row_group_limit:
                        self.flush_row_group()
        except Exception:
            records.clear()
            raise

    def write_csv_rows(self, rows: list[tuple[str | None, ...]]) -> None:
        """Convert canonical parser rows without rebuilding typed objects."""
        if self._writer is None or self.schema is None:
            raise RuntimeError('B3 Parquet writer session is not open')

        try:
            while rows:
                size = min(len(rows), RECORD_BATCH_LIMIT)
                chunk = rows[:size]
                del rows[:size]
                for batch in self._csv_rows_to_batches(chunk, self.schema):
                    self._pending_batches.append(batch)
                    self._pending_rows += batch.num_rows
                    if self._pending_rows >= self.row_group_limit:
                        self.flush_row_group()
        except Exception:
            rows.clear()
            raise

    @staticmethod
    def _records_to_batches(
        records: list[dict[str, object]], schema: Schema
    ) -> list[Any]:
        """Convert typed records through Arrow CSV without importing pandas.

        PyArrow's Python-list constructors import ``pandas_compat`` in the
        supported runtime, which violates the package's lazy pandas boundary.
        A bounded CSV bridge keeps conversion inside PyArrow, applies the
        explicit schema, and still raises on incompatible values instead of
        silently coercing them.
        """
        return B3ParquetWriterSession._csv_rows_to_batches(
            [_serialize_record(record, schema.names) for record in records],
            schema,
            allow_internal_sentinel=True,
        )

    @staticmethod
    def _csv_rows_to_batches(
        rows: Iterable[Iterable[str | None]],
        schema: Schema,
        *,
        allow_internal_sentinel: bool = False,
    ) -> list[Any]:
        """Feed canonical string rows to Arrow CSV with explicit types."""
        pa, pacsv, _ = _get_arrow()

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator='\n')
        column_names = tuple(schema.names)
        for row_number, row in enumerate(rows, start=1):
            row_values = list(row)
            if not allow_internal_sentinel:
                _reject_reserved_sentinel(row_values, column_names, row_number)
            writer.writerow(
                _NULL_SENTINEL if value is None else value
                for value in row_values
            )
        table = pacsv.read_csv(
            pa.py_buffer(buffer.getvalue().encode('utf-8')),
            read_options=pacsv.ReadOptions(
                column_names=list(schema.names),
                use_threads=False,
            ),
            parse_options=pacsv.ParseOptions(delimiter=','),
            convert_options=pacsv.ConvertOptions(
                column_types=schema,
                null_values=[_NULL_SENTINEL],
                strings_can_be_null=True,
                quoted_strings_can_be_null=False,
            ),
        )
        return list(table.to_batches(max_chunksize=RECORD_BATCH_LIMIT))

    def write_batches(self, batches: Iterable[Any]) -> None:
        """Copy already-typed Arrow batches into this bounded session."""
        if self._writer is None or self.schema is None:
            raise RuntimeError('B3 Parquet writer session is not open')
        for batch in batches:
            if batch.schema != self.schema:
                raise ExtractionError(
                    str(self.path), 'B3 source Parquet schema is incompatible'
                )
            self._pending_batches.append(batch)
            self._pending_rows += batch.num_rows
            if self._pending_rows >= self.row_group_limit:
                self.flush_row_group()

    def flush_row_group(self) -> None:
        """Persist at most one bounded Arrow row group."""
        if not self._pending_batches:
            return
        if self._writer is None or self.schema is None:
            raise RuntimeError('B3 Parquet writer session is not open')
        pa, _, _ = _get_arrow()
        table = pa.Table.from_batches(
            self._pending_batches, schema=self.schema
        )
        offset = 0
        while offset < table.num_rows:
            size = min(self.row_group_limit, table.num_rows - offset)
            self._writer.write_table(
                table.slice(offset, size), row_group_size=self.row_group_limit
            )
            self.rows_written += size
            offset += size
        self._pending_batches.clear()
        self._pending_rows = 0

    def close(self) -> None:
        """Flush, close, and validate the one artifact exactly once."""
        if self._state == 'NEW':
            raise RuntimeError('B3 Parquet writer session has not been opened')
        if self._state == 'CLOSED':
            self._pending_batches.clear()
            self._pending_rows = 0
            self._writer = None
            return
        try:
            self.flush_row_group()
            if self._writer is not None:
                writer = self._writer
                self._writer = None
                writer.close()
            self._pending_batches.clear()
            self._pending_rows = 0
            self.validate()
        finally:
            if self._writer is not None:
                writer = self._writer
                self._writer = None
                with suppress(Exception):
                    writer.close()
            self._pending_batches.clear()
            self._pending_rows = 0
            self._state = 'CLOSED'

    def validate(self) -> None:
        """Reopen the artifact and prove schema and row-count integrity."""
        if self.path is None or self.schema is None:
            raise RuntimeError('B3 Parquet writer session has no artifact')
        _, _, pq = _get_arrow()
        parquet = pq.ParquetFile(self.path)
        metadata = parquet.metadata
        if metadata is None or metadata.num_rows != self.rows_written:
            raise ExtractionError(
                str(self.path), 'B3 Parquet row count validation failed'
            )
        if parquet.schema_arrow != self.schema:
            raise ExtractionError(
                str(self.path), 'B3 Parquet schema validation failed'
            )
        if b'pandas' in (parquet.schema_arrow.metadata or {}):
            raise ExtractionError(
                str(self.path),
                'B3 Parquet unexpectedly contains pandas metadata',
            )


def _serialize_record(
    record: dict[str, object], column_names: Iterable[str]
) -> list[str]:
    """Serialize one typed record for the private Arrow CSV bridge."""
    values: list[str] = []
    for name in column_names:
        value = record[name]
        if value is None:
            values.append(_NULL_SENTINEL)
        elif isinstance(value, date):
            values.append(value.isoformat())
        elif isinstance(value, Decimal):
            values.append(format(value, 'f'))
        else:
            serialized = str(value)
            if serialized == _NULL_SENTINEL:
                raise ExtractionError(
                    'B3 Parquet',
                    'Reserved null sentinel is not valid input data: '
                    f'column={name!r}',
                )
            values.append(serialized)
    return values


def _reject_reserved_sentinel(
    values: list[str | None], column_names: Iterable[str], row_number: int
) -> None:
    """Reject the private null marker when it arrives as real CSV data."""
    names = tuple(column_names)
    for index, value in enumerate(values):
        if value == _NULL_SENTINEL:
            column = names[index] if index < len(names) else str(index)
            raise ExtractionError(
                'B3 Parquet',
                'Reserved null sentinel is not valid input data: '
                f'row={row_number}; column={column!r}',
            )
