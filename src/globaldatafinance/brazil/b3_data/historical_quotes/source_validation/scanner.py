"""Scan source lines and collect independent row summaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..cotahist_parser import CotahistParserB3
from ..integrity import B3RawLine
from ..row_digest import B3OrderedRowDigest
from ..zip_reader import _OpenedCotahistSource
from .control_records import (
    HEADER_SIZE,
    line_error,
    validate_header,
    validate_trailer,
)


@dataclass
class ScannedDocument:
    """Hold parser metrics and row digests for a scanned source."""

    parser: CotahistParserB3 = field(default_factory=CotahistParserB3)
    rows_digest: B3OrderedRowDigest = field(default_factory=B3OrderedRowDigest)
    content_hash: Any = field(default_factory=hashlib.sha256)
    header: bytes | None = None
    trailer: bytes | None = None
    generation_date: date | None = None
    declared_records: int | None = None
    state: str = 'before_header'
    quote_count: int = 0
    blank_lines: int = 0
    content_bytes: int = 0
    first_date: str | None = None
    last_date: str | None = None


def scan_document(
    source: _OpenedCotahistSource,
    year: int,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    content_sha256: str,
) -> ScannedDocument:
    """Scan one document and accumulate parser and digest results."""
    scanned = ScannedDocument()
    for raw_line in source.iter_raw_lines():
        scanned.content_hash.update(raw_line.complete_bytes)
        scanned.content_bytes += len(raw_line.complete_bytes)
        if not raw_line.content:
            scanned.blank_lines += 1
            continue
        _validate_record_width(raw_line)
        _scan_record(
            raw_line,
            year,
            target_tpmerc_codes,
            all_markets,
            content_sha256,
            scanned,
        )
    return scanned


def _validate_record_width(raw_line: B3RawLine) -> None:
    if len(raw_line.content) == HEADER_SIZE:
        return
    cause = f'Expected exactly {HEADER_SIZE} bytes'
    try:
        latin1_content = raw_line.content.decode('utf-8').encode('latin-1')
    except (UnicodeDecodeError, UnicodeEncodeError):
        latin1_content = b''
    if len(latin1_content) == HEADER_SIZE:
        cause += (
            '; detected UTF-8 text that has the expected width in Latin-1. '
            'Keep the original source and create a separate Latin-1 copy '
            'before extraction'
        )
    raise line_error(
        raw_line.context,
        'record_length',
        str(len(raw_line.content)),
        cause,
    )


def _scan_record(
    raw_line: B3RawLine,
    year: int,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    content_sha256: str,
    scanned: ScannedDocument,
) -> None:
    record_type = raw_line.content[:2]
    if record_type == b'00':
        _scan_header(raw_line, year, scanned)
    elif record_type == b'01':
        _scan_quote(
            raw_line,
            year,
            target_tpmerc_codes,
            all_markets,
            content_sha256,
            scanned,
        )
    elif record_type == b'99':
        _scan_trailer(raw_line, year, scanned)
    else:
        raise line_error(
            raw_line.context,
            'record_type',
            record_type.decode('latin-1'),
            'Unsupported non-empty COTAHIST record type',
        )


def _scan_header(
    raw_line: B3RawLine, year: int, scanned: ScannedDocument
) -> None:
    if scanned.state != 'before_header':
        raise line_error(
            raw_line.context,
            'record_type',
            '00',
            'Header is repeated or misplaced',
        )
    scanned.generation_date = validate_header(
        raw_line.content, year, raw_line.context
    )
    scanned.header = raw_line.content
    scanned.state = 'quotes'


def _scan_quote(
    raw_line: B3RawLine,
    year: int,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    content_sha256: str,
    scanned: ScannedDocument,
) -> None:
    if scanned.state != 'quotes':
        raise line_error(
            raw_line.context,
            'record_type',
            '01',
            'Quotation is before the header or after the trailer',
        )
    parsed = scanned.parser._parse_bytes_to_csv_row(
        raw_line.content,
        target_tpmerc_codes,
        context=raw_line.context,
        all_markets=all_markets,
        source_year=year,
        source_sha256=content_sha256,
    )
    if parsed is not None:
        scanned.rows_digest.update(parsed)
    scanned.quote_count += 1
    trading_date = raw_line.content[2:10].decode('ascii')
    scanned.first_date = (
        trading_date
        if scanned.first_date is None
        else min(scanned.first_date, trading_date)
    )
    scanned.last_date = (
        trading_date
        if scanned.last_date is None
        else max(scanned.last_date, trading_date)
    )


def _scan_trailer(
    raw_line: B3RawLine, year: int, scanned: ScannedDocument
) -> None:
    if scanned.state != 'quotes' or scanned.quote_count == 0:
        raise line_error(
            raw_line.context,
            'record_type',
            '99',
            'Trailer is repeated, misplaced, or has no quotes',
        )
    header = scanned.header
    if header is None:
        raise line_error(
            raw_line.context,
            'record_type',
            '99',
            'Trailer appears before the header',
        )
    scanned.declared_records = validate_trailer(
        raw_line.content,
        year,
        header,
        raw_line.context,
    )
    scanned.trailer = raw_line.content
    scanned.state = 'finished'
