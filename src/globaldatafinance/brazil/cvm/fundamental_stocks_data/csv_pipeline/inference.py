"""Global CVM CSV structure validation and Arrow schema inference."""

from __future__ import annotations

import csv
from pathlib import Path

import pyarrow as pa

from .....macro_exceptions import DiskFullError, ExtractionError
from .models import ColumnInference, CsvAnalysis, EncodingPlan
from .source import ReopenableCsvSource, text_source


def analyse_csv(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
) -> CsvAnalysis:
    """Read all source rows as text and retain global type observations."""
    reader = None
    try:
        with text_source(source, utf8_source, plan) as text:
            reader = csv.reader(
                text,
                delimiter=';',
                quoting=csv.QUOTE_NONE,
                strict=True,
            )
            try:
                header = tuple(next(reader))
            except StopIteration as error:
                raise ExtractionError(
                    str(source.source_path), 'CSV member has no header'
                ) from error
            validate_header(header)
            columns = [ColumnInference() for _ in header]
            rows = 0
            short_rows_seen = False
            physical_lines = reader.line_num
            for logical_record, row in enumerate(reader, start=1):
                physical_lines = reader.line_num
                if len(row) > len(header):
                    raise_structure_error(
                        source,
                        logical_record,
                        reader.line_num,
                        len(header),
                        len(row),
                        row,
                    )
                if len(row) < len(header):
                    short_rows_seen = True
                    row = [*row, *([''] * (len(header) - len(row)))]
                for index, value in enumerate(row):
                    columns[index].observe(value)
                rows += 1
    except csv.Error as error:
        line = reader.line_num if reader is not None else 0
        raise_csv_error(source, line, error)
    return CsvAnalysis(
        header=header,
        columns=columns,
        rows=rows,
        short_rows_seen=short_rows_seen,
        physical_lines=physical_lines,
    )


def normalize_short_rows(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
    staging_dir: Path,
    header: tuple[str, ...],
) -> Path:
    """Create a private CSV that pads only short trailing fields."""
    normalized = staging_dir / '.cvm-normalized.csv'
    reader = None
    try:
        with (
            text_source(source, utf8_source, plan) as text,
            normalized.open('w', encoding='utf-8', newline='') as target,
        ):
            reader = csv.reader(
                text,
                delimiter=';',
                quoting=csv.QUOTE_NONE,
                strict=True,
            )
            observed_header = tuple(next(reader))
            if observed_header != header:
                raise ExtractionError(
                    str(source.source_path),
                    'CSV header changed while normalizing short rows',
                )
            writer = csv.writer(
                target,
                delimiter=';',
                quoting=csv.QUOTE_NONE,
                lineterminator='\n',
            )
            writer.writerow(header)
            for logical_record, row in enumerate(reader, start=1):
                if len(row) > len(header):
                    raise_structure_error(
                        source,
                        logical_record,
                        reader.line_num,
                        len(header),
                        len(row),
                        row,
                    )
                padded_row = [
                    *row,
                    *([''] * (len(header) - len(row))),
                ]
                if not row and len(header) == 1:
                    target.write('\n')
                else:
                    writer.writerow(padded_row)
    except csv.Error as error:
        line = reader.line_num if reader is not None else 0
        raise_csv_error(source, line, error)
    except OSError as error:
        if getattr(error, 'errno', None) == 28:
            raise DiskFullError(str(normalized)) from error
        raise ExtractionError(
            str(source.source_path),
            f'Could not normalize short CSV rows: {error}',
        ) from error
    return normalized


def build_schema(analysis: CsvAnalysis) -> pa.Schema:
    """Build one explicit Arrow schema from global column observations."""
    fields = [
        pa.field(name, inferred_type(column, analysis.rows))
        for name, column in zip(analysis.header, analysis.columns, strict=True)
    ]
    return pa.schema(fields)


def inferred_type(column: ColumnInference, rows: int) -> pa.DataType:
    """Select the documented lossless Arrow type for one column."""
    if rows == 0:
        return pa.null()
    if not column.has_non_null:
        return pa.float64()
    if (
        column.has_string
        or column.has_signed_overflow
        or column.has_unsigned_overflow
    ):
        return pa.string()
    if column.has_boolean:
        mixed_with_boolean = (
            column.has_signed_integer
            or column.has_unsigned_integer
            or column.has_float
        )
        return pa.string() if mixed_with_boolean else pa.bool_()
    if column.has_float:
        return pa.float64()
    if column.has_unsigned_integer:
        if column.has_null or column.has_signed_integer:
            return pa.string()
        return pa.uint64()
    return pa.int64()


def validate_header(header: tuple[str, ...]) -> None:
    """Reject absent, unusable, and duplicate column names before writing."""
    if not header or not any(column for column in header):
        raise ExtractionError('CVM CSV', 'CSV member has no usable header')
    if len(set(header)) != len(header):
        raise ExtractionError(
            'CVM CSV', 'CSV member has duplicate header column names'
        )


def raise_structure_error(
    source: ReopenableCsvSource,
    record: int,
    line: int,
    expected: int,
    observed: int,
    row: list[str],
) -> None:
    """Raise a bounded source-context error for an invalid row."""
    preview = ';'.join(row)[:80]
    raise ExtractionError(
        str(source.source_path),
        f'CSV structure error source={source.source_path.name}; '
        f'member={source.member_name}; record={record}; line={line}; '
        f'expected_fields={expected}; observed_fields={observed}; '
        f'value={preview!r}',
    )


def raise_csv_error(
    source: ReopenableCsvSource,
    line: int,
    error: csv.Error,
) -> None:
    """Wrap strict CSV dialect errors with bounded source coordinates."""
    raise ExtractionError(
        str(source.source_path),
        f'CSV parser error source={source.source_path.name}; '
        f'member={source.member_name}; line={line}; cause={error}',
    ) from error
