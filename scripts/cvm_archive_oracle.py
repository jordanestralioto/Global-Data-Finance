"""Independent full-record reconciliation of CVM archives and Parquets."""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import zipfile
from collections.abc import Iterator
from itertools import zip_longest
from pathlib import Path, PurePosixPath
from typing import IO, Any

import pyarrow as pa
import pyarrow.parquet as pq

_FIELD_LIMIT = 8 * 1024 * 1024
_UNDEFINED_CP1252 = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})
_DEFINED_CP1252 = frozenset(range(0x80, 0xA0)) - _UNDEFINED_CP1252


def reconcile_archive(source: Path, destination: Path) -> dict[str, Any]:
    """Compare all CSV fields, including order, with the produced Parquets.

    This oracle uses Python's CSV parser and independently selects encoding;
    it does not use the product pipeline, schema builder, or content checker.
    """
    original_field_limit = csv.field_size_limit(_FIELD_LIMIT)
    try:
        with zipfile.ZipFile(source) as archive:
            members = [
                reconcile_member(archive, info, destination)
                for info in archive.infolist()
                if not info.is_dir()
            ]
    finally:
        csv.field_size_limit(original_field_limit)
    csv_members = [member for member in members if member['isCsv']]
    if not csv_members:
        raise ValueError('CVM archive oracle found no CSV members')
    expected = {member['parquetName'] for member in csv_members}
    observed = {path.name for path in destination.glob('*.parquet')}
    if observed != expected:
        raise ValueError(
            'CVM artifact inventory differs from archive CSV inventory: '
            f'missing={sorted(expected - observed)}; '
            f'extra={sorted(observed - expected)}'
        )
    return {
        'status': 'passed',
        'memberCount': len(members),
        'csvCount': len(csv_members),
        'attachmentCount': len(members) - len(csv_members),
        'recordCount': sum(member.get('rows', 0) for member in members),
        'comparedFieldCount': sum(
            member.get('comparedFieldCount', 0) for member in members
        ),
        'members': members,
    }


def reconcile_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
) -> dict[str, Any]:
    """Fingerprint every member and reconcile CSV members against output."""
    is_csv = info.filename.casefold().endswith('.csv')
    with archive.open(info) as raw:
        digest, encoding = _inspect_raw_member(raw, require_text=is_csv)
    evidence: dict[str, Any] = {
        'name': info.filename,
        'sizeBytes': info.file_size,
        'compressedBytes': info.compress_size,
        'crc32': f'{info.CRC:08x}',
        'sha256': digest,
        'isCsv': is_csv,
    }
    if not is_csv:
        return evidence
    name = PurePosixPath(info.filename.replace('\\', '/')).stem + '.parquet'
    path = destination / name
    with archive.open(info) as raw:
        evidence.update(_compare_records(raw, encoding, path))
    evidence.update({'parquetName': name, 'encoding': encoding})
    return evidence


def _inspect_raw_member(
    raw: IO[bytes], *, require_text: bool
) -> tuple[str, str]:
    """Hash raw bytes and independently check the documented codec policy."""
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
    valid_utf8 = True
    defined_cp1252 = False
    undefined_cp1252 = False
    prefix = b''
    while chunk := raw.read(64 * 1024):
        digest.update(chunk)
        if not require_text:
            continue
        if len(prefix) < 3:
            prefix += chunk[: 3 - len(prefix)]
        defined_cp1252 |= any(byte in chunk for byte in _DEFINED_CP1252)
        undefined_cp1252 |= any(byte in chunk for byte in _UNDEFINED_CP1252)
        if valid_utf8:
            try:
                decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                valid_utf8 = False
    encoding = _select_encoding(
        decoder,
        valid_utf8,
        prefix,
        defined_cp1252,
        undefined_cp1252,
        require_text=require_text,
    )
    return digest.hexdigest(), encoding


def _select_encoding(
    decoder: Any,
    valid_utf8: bool,
    prefix: bytes,
    defined_cp1252: bool,
    undefined_cp1252: bool,
    *,
    require_text: bool,
) -> str:
    """Finish strict decoding and select the independently checked codec."""
    if not require_text:
        return 'binary'
    if valid_utf8:
        try:
            decoder.decode(b'', final=True)
        except UnicodeDecodeError:
            valid_utf8 = False
    if prefix.startswith(codecs.BOM_UTF8):
        if not valid_utf8:
            raise ValueError('CVM oracle found invalid UTF-8 after a BOM')
        encoding = 'utf-8-sig'
    elif valid_utf8:
        encoding = 'utf-8'
    elif undefined_cp1252 or not defined_cp1252:
        encoding = 'latin-1'
    else:
        encoding = 'cp1252'
    return encoding


def _compare_records(
    raw: IO[bytes], encoding: str, path: Path
) -> dict[str, Any]:
    """Require exact header and value equality for every source record."""
    with (
        io.TextIOWrapper(
            raw, encoding=encoding, errors='strict', newline=''
        ) as text,
        pq.ParquetFile(path, page_checksum_verification=True) as parquet,
    ):
        reader = csv.reader(text, delimiter=';', quoting=csv.QUOTE_NONE)
        header = next(reader)
        if header != parquet.schema_arrow.names:
            raise ValueError(f'CVM source/Parquet header mismatch: {path}')
        if not all(
            pa.types.is_string(field.type) for field in parquet.schema_arrow
        ):
            raise ValueError(f'CVM output is not exact text: {path}')
        row_count, short_rows, logical_digest = _compare_rows(
            reader, _parquet_rows(parquet), len(header), path
        )
        if parquet.metadata.num_rows != row_count:
            raise ValueError(f'CVM source/Parquet metadata mismatch: {path}')
    return {
        'rows': row_count,
        'columns': header,
        'comparedFieldCount': row_count * len(header),
        'shortRowsPadded': short_rows,
        'logicalSha256': logical_digest,
    }


def _compare_rows(
    source_rows: Iterator[list[str]],
    output_rows: Iterator[list[str]],
    width: int,
    path: Path,
) -> tuple[int, int, str]:
    """Reject lost, added, reordered, truncated, or changed records."""
    digest = hashlib.sha256()
    row_count = 0
    short_rows = 0
    for index, (source_row, output_row) in enumerate(
        zip_longest(source_rows, output_rows), start=1
    ):
        if source_row is None or output_row is None:
            raise ValueError(
                f'CVM source/Parquet record count mismatch: {path}; '
                f'record={index}'
            )
        if len(source_row) > width:
            raise ValueError(f'CVM oracle found an over-wide record: {path}')
        short_rows += len(source_row) < width
        expected = source_row + [''] * (width - len(source_row))
        if expected != output_row:
            raise ValueError(
                f'CVM source/Parquet field mismatch: {path}; record={index}'
            )
        digest.update((';'.join(expected) + '\n').encode('utf-8'))
        row_count += 1
    return row_count, short_rows, digest.hexdigest()


def _parquet_rows(parquet: Any) -> Iterator[list[str]]:
    """Yield output records with memory bounded by the stored row groups."""
    max_rows = max(
        (
            parquet.metadata.row_group(index).num_rows
            for index in range(parquet.metadata.num_row_groups)
        ),
        default=1,
    )
    for batch in parquet.iter_batches(
        batch_size=max(1, min(8192, max_rows)), use_threads=False
    ):
        columns = [column.to_pylist() for column in batch.columns]
        for row in zip(*columns, strict=True):
            yield list(row)
