"""Assemble a validated COTAHIST source document."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .....macro_exceptions import ExtractionError
from ..integrity import sha256_file
from ..models import B3SourceWarning, ValidatedCotahistSource
from ..zip_reader import ZipFileReaderB3
from .control_records import trailer_convention
from .scanner import ScannedDocument, scan_document


class CotahistDocumentValidator:
    """Validate source structure and every quote before output creation."""

    def __init__(self, reader: ZipFileReaderB3) -> None:
        """Bind the bounded reader used for every preflight pass."""
        self._reader = reader

    def validate(
        self,
        path: Path,
        *,
        year: int,
        member: str,
        target_tpmerc_codes: set[str],
        all_markets: bool,
    ) -> ValidatedCotahistSource:
        """Return immutable facts only after the complete source is valid."""
        outer_sha256 = sha256_file(path)
        content_sha256, uncompressed_bytes = _sha256_uncompressed(
            self._reader, path, member
        )
        scanned = scan_document(
            self._reader,
            path,
            year,
            member,
            target_tpmerc_codes,
            all_markets,
            content_sha256,
        )
        trailer_convention = _validate_scanned_document(
            path,
            outer_sha256,
            content_sha256,
            uncompressed_bytes,
            scanned,
        )
        warnings = _source_warnings(scanned, trailer_convention)
        return _validated_source(
            path,
            year,
            member,
            outer_sha256,
            content_sha256,
            uncompressed_bytes,
            trailer_convention,
            scanned,
            warnings,
        )


def _validate_scanned_document(
    path: Path,
    outer_sha256: str,
    content_sha256: str,
    uncompressed_bytes: int,
    scanned: ScannedDocument,
) -> str:
    _validate_document_completion(path, scanned)
    if scanned.content_hash.hexdigest() != content_sha256:
        raise ExtractionError(
            path.name, 'COTAHIST content changed during catalog preflight'
        )
    if scanned.content_bytes != uncompressed_bytes:
        raise ExtractionError(
            path.name,
            'COTAHIST uncompressed byte count changed during preflight',
        )
    if sha256_file(path) != outer_sha256:
        raise ExtractionError(
            path.name, 'COTAHIST input changed during catalog preflight'
        )
    declared = scanned.declared_records
    if declared is None:
        raise RuntimeError('Validated trailer is missing its declared count')
    count_convention = trailer_convention(declared, scanned.quote_count)
    if count_convention is None:
        raise ExtractionError(
            path.name,
            'COTAHIST trailer declared an unsupported record total: '
            f'declared={declared}; quotations={scanned.quote_count}',
        )
    _validate_parser_accounting(path, scanned)
    return count_convention


def _validate_document_completion(
    path: Path, scanned: ScannedDocument
) -> None:
    if (
        scanned.state != 'finished'
        or scanned.header is None
        or scanned.trailer is None
    ):
        raise ExtractionError(
            path.name,
            'COTAHIST document must contain one header, at least one '
            'quotation, one trailer, and then end of document',
        )


def _validate_parser_accounting(path: Path, scanned: ScannedDocument) -> None:
    metrics = scanned.parser.metrics
    if (
        metrics.raw_quotes != scanned.quote_count
        or metrics.raw_quotes
        != metrics.selected_records + metrics.filtered_records
        or metrics.parsed_records != metrics.selected_records
    ):
        raise ExtractionError(
            path.name,
            'COTAHIST preflight quotation accounting invariant failed',
        )


def _source_warnings(
    scanned: ScannedDocument, trailer_convention: str
) -> list[B3SourceWarning]:
    warnings: list[B3SourceWarning] = []
    if scanned.blank_lines:
        warnings.append(
            B3SourceWarning(
                'BLANK_PHYSICAL_LINES',
                scanned.blank_lines,
                'Empty physical lines were counted and ignored.',
            )
        )
    if trailer_convention == 'quotes_only':
        warnings.append(
            B3SourceWarning(
                'TRAILER_QUOTES_ONLY',
                1,
                'Trailer count includes quotations but omits the header '
                'and trailer controls.',
            )
        )
    warnings.extend(
        B3SourceWarning(
            'UNKNOWN_TPMERC',
            count,
            f'Unknown numeric TPMERC {code} was preserved or '
            'intentionally excluded by the requested selection.',
        )
        for code, count in sorted(
            scanned.parser.metrics.unknown_market_counts.items()
        )
    )
    return warnings


def _validated_source(
    path: Path,
    year: int,
    member: str,
    outer_sha256: str,
    content_sha256: str,
    uncompressed_bytes: int,
    trailer_convention: str,
    scanned: ScannedDocument,
    warnings: list[B3SourceWarning],
) -> ValidatedCotahistSource:
    metrics = scanned.parser.metrics
    if scanned.first_date is None or scanned.last_date is None:
        raise RuntimeError('Validated source has no trading date range')
    if scanned.header is None or scanned.trailer is None:
        raise RuntimeError('Validated source is missing its control records')
    if scanned.declared_records is None or scanned.generation_date is None:
        raise RuntimeError('Validated source is missing its control metadata')
    return ValidatedCotahistSource(
        path=path,
        year=year,
        member=member,
        outer_sha256=outer_sha256,
        content_sha256=content_sha256,
        uncompressed_bytes=uncompressed_bytes,
        expected_rows_sha256=scanned.rows_digest.hexdigest(),
        raw_quotes=scanned.quote_count,
        selected_quotes=metrics.selected_records,
        intentional_exclusions=metrics.filtered_records,
        market_counts=tuple(sorted(metrics.market_counts.items())),
        unknown_market_counts=tuple(
            sorted(metrics.unknown_market_counts.items())
        ),
        header_bytes=scanned.header,
        trailer_bytes=scanned.trailer,
        generation_date=scanned.generation_date,
        declared_records=scanned.declared_records,
        trailer_convention=trailer_convention,
        blank_lines=scanned.blank_lines,
        first_trading_date=scanned.first_date,
        last_trading_date=scanned.last_date,
        warnings=tuple(warnings),
    )


def _sha256_uncompressed(
    reader: ZipFileReaderB3,
    path: Path,
    member: str,
) -> tuple[str, int]:
    """Hash the complete uncompressed physical stream before parsing rows."""
    digest = hashlib.sha256()
    byte_count = 0
    for raw_line in reader.iter_raw_lines(str(path), expected_member=member):
        digest.update(raw_line.complete_bytes)
        byte_count += len(raw_line.complete_bytes)
    return digest.hexdigest(), byte_count
