"""Complete CVM CSV structure checks and exact-text Arrow schemas."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from .....macro_exceptions import DiskFullError, ExtractionError
from ..content_fingerprint import CONTRACT_VERSION, RecordDigest
from .constants import MAX_COLUMNS
from .models import CsvAnalysis, EncodingPlan
from .records import read_records
from .source import ReopenableCsvSource, text_source


def analyse_csv(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
) -> CsvAnalysis:
    """Validate every record and fingerprint all decoded source fields."""
    with text_source(source, utf8_source, plan) as text:
        reader = read_records(text, str(source.source_path))
        try:
            header = tuple(next(reader))
        except StopIteration as error:
            raise ExtractionError(
                str(source.source_path), 'CSV member has no header'
            ) from error
        validate_header(header)
        digest = RecordDigest(header)
        rows = 0
        max_record_bytes = len(';'.join(header).encode('utf-8')) + 2
        short_rows_seen = False
        for record, row in enumerate(reader, start=1):
            row, short = pad_record(source, header, record, row)
            short_rows_seen |= short
            digest.update(row)
            max_record_bytes = max(
                max_record_bytes,
                len(';'.join(row).encode('utf-8')) + 2,
            )
            rows += 1
    return CsvAnalysis(
        header=header,
        rows=rows,
        content_sha256=digest.hexdigest(),
        max_record_bytes=max_record_bytes,
        short_rows_seen=short_rows_seen,
        physical_lines=rows + 1,
    )


def normalize_short_rows(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
    staging_dir: Path,
    header: tuple[str, ...],
) -> Path:
    """Pad absent trailing fields in a private UTF-8 CSV spool."""
    normalized = staging_dir / '.cvm-normalized.csv'
    try:
        with (
            text_source(source, utf8_source, plan) as text,
            normalized.open('w', encoding='utf-8', newline='') as target,
        ):
            reader = read_records(text, str(source.source_path))
            if tuple(next(reader)) != header:
                raise ExtractionError(
                    str(source.source_path),
                    'CSV header changed while normalizing short rows',
                )
            target.write(';'.join(header) + '\n')
            for record, row in enumerate(reader, start=1):
                padded, _ = pad_record(source, header, record, row)
                target.write(';'.join(padded) + '\n')
    except OSError as error:
        if getattr(error, 'errno', None) == 28:
            raise DiskFullError(str(normalized)) from error
        raise ExtractionError(
            str(source.source_path),
            f'Could not normalize short CSV rows: {error}',
        ) from error
    return normalized


def build_schema(analysis: CsvAnalysis) -> pa.Schema:
    """Keep every field as text, including empty and header-only columns."""
    return pa.schema(
        [pa.field(name, pa.string()) for name in analysis.header],
        metadata={
            b'cvm.contract': CONTRACT_VERSION,
            b'cvm.content-sha256': analysis.content_sha256.encode('ascii'),
        },
    )


def validate_header(header: tuple[str, ...]) -> None:
    """Reject absent, unusable, duplicate, and excessively wide headers."""
    if not header or not all(column.strip() for column in header):
        raise ExtractionError('CVM CSV', 'CSV member has no usable header')
    if len(header) > MAX_COLUMNS:
        raise ExtractionError(
            'CVM CSV', f'CSV header exceeds {MAX_COLUMNS} columns'
        )
    if len(set(header)) != len(header):
        raise ExtractionError(
            'CVM CSV', 'CSV member has duplicate header column names'
        )


def pad_record(
    source: ReopenableCsvSource,
    header: tuple[str, ...],
    record: int,
    row: list[str],
) -> tuple[list[str], bool]:
    """Reject extra fields and pad absent trailing fields with empty text."""
    if len(row) > len(header):
        preview = ';'.join(row)[:80]
        raise ExtractionError(
            str(source.source_path),
            f'CSV structure error source={source.source_path.name}; '
            f'member={source.member_name}; record={record}; '
            f'line={record + 1}; '
            f'expected_fields={len(header)}; observed_fields={len(row)}; '
            f'value={preview!r}',
        )
    short = len(row) < len(header)
    return [*row, *([''] * (len(header) - len(row)))], short
