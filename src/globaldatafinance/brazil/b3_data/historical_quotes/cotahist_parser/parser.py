"""Strict orchestration for B3 COTAHIST quotation records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from .....macro_exceptions import ExtractionError
from ..integrity import COTAHIST_RECORD_WIDTH, B3RecordContext
from ..layout import B3_FIELD_NAMES
from .field_conversion import (
    CsvRow,
    canonical_row,
    field_error,
    typed_record,
)

_EXPECTED_LENGTH = COTAHIST_RECORD_WIDTH
_MARKET_INDEX = B3_FIELD_NAMES.index('tipo_mercado')
_TRADING_DATE_INDEX = B3_FIELD_NAMES.index('data_pregao')

_KNOWN_TPMERC_CODES = frozenset(
    {
        '010',
        '020',
        '070',
        '080',
        '030',
        '012',
        '013',
        '050',
        '060',
        '017',
        '021',
    }
)


@dataclass
class B3ParserMetrics:
    """Per-source record classification counts produced by the parser."""

    blank_lines: int = 0
    header_records: int = 0
    trailer_records: int = 0
    raw_quotes: int = 0
    filtered_records: int = 0
    selected_records: int = 0
    parsed_records: int = 0
    market_counts: dict[str, int] = field(default_factory=dict)
    unknown_market_counts: dict[str, int] = field(default_factory=dict)


class CotahistParserB3:
    """Validate complete quotation records before applying market selection."""

    EXPECTED_LINE_LENGTH = _EXPECTED_LENGTH

    def __init__(self) -> None:
        """Initialize source-local classification metrics."""
        self.metrics = B3ParserMetrics()

    @property
    def filtered_records(self) -> int:
        """Return valid quotations intentionally excluded by selection."""
        return self.metrics.filtered_records

    def parse_line(
        self,
        line: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None = None,
        *,
        all_markets: bool = False,
        source_year: int | None = None,
        source_sha256: str = '',
    ) -> dict[str, Any] | None:
        """Return a typed row while preserving the string-reader contract."""
        row = self.parse_line_to_csv_row(
            line,
            target_tpmerc_codes,
            context=context,
            all_markets=all_markets,
            source_year=source_year,
            source_sha256=source_sha256,
        )
        return None if row is None else typed_record(row)

    def parse_line_to_csv_row(
        self,
        line: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None = None,
        *,
        all_markets: bool = False,
        source_year: int | None = None,
        source_sha256: str = '',
    ) -> CsvRow | None:
        """Validate and normalize one line in canonical schema order.

        Selection occurs only after every source field has passed validation,
        so malformed data in an excluded market still fails the extraction.
        """
        normalized = _remove_one_line_terminator(line)
        return self._parse_normalized_line(
            normalized,
            target_tpmerc_codes,
            context,
            all_markets,
            source_year,
            source_sha256,
            None,
        )

    def _parse_bytes_to_csv_row(
        self,
        content: bytes,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None = None,
        *,
        all_markets: bool = False,
        source_year: int | None = None,
        source_sha256: str = '',
    ) -> CsvRow | None:
        """Decode and retain the same source bytes without re-encoding them."""
        if type(self) is not CotahistParserB3:
            return self.parse_line_to_csv_row(
                content.decode('latin-1'),
                target_tpmerc_codes,
                context,
                all_markets=all_markets,
                source_year=source_year,
                source_sha256=source_sha256,
            )
        original = content.removesuffix(b'\r\n').removesuffix(b'\n')
        original = original.removesuffix(b'\r')
        return self._parse_normalized_line(
            original.decode('latin-1'),
            target_tpmerc_codes,
            context,
            all_markets,
            source_year,
            source_sha256,
            original,
        )

    def _parse_normalized_line(
        self,
        normalized: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None,
        all_markets: bool,
        source_year: int | None,
        source_sha256: str,
        original_record: bytes | None,
    ) -> CsvRow | None:
        """Share validation, metrics and selection across entrypoints."""
        if not normalized:
            self.metrics.blank_lines += 1
            return None
        record_type = normalized[:2]
        if record_type == '00':
            self.metrics.header_records += 1
            return None
        if record_type == '99':
            self.metrics.trailer_records += 1
            return None
        if record_type != '01':
            raise self._record_error(
                context,
                normalized,
                record_type,
                'record_type',
                record_type,
                'Unsupported non-empty COTAHIST record type',
            )
        return self._parse_quote(
            normalized,
            target_tpmerc_codes,
            context,
            all_markets,
            source_year,
            source_sha256,
            original_record,
        )

    def _parse_quote(
        self,
        normalized: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None,
        all_markets: bool,
        source_year: int | None,
        source_sha256: str,
        original_record: bytes | None,
    ) -> CsvRow | None:
        """Validate one quotation and apply market selection."""
        record_type = normalized[:2]
        self.metrics.raw_quotes += 1
        if len(normalized) != _EXPECTED_LENGTH:
            raise self._record_error(
                context,
                normalized,
                record_type,
                'record_length',
                str(len(normalized)),
                f'Expected exactly {_EXPECTED_LENGTH} characters',
            )
        if original_record is None:
            try:
                original_record = normalized.encode('latin-1')
            except UnicodeEncodeError as error:
                raise self._record_error(
                    context,
                    normalized,
                    record_type,
                    'record_encoding',
                    normalized[:80],
                    error,
                ) from error

        source_context = context or B3RecordContext('', '', 0, 0)
        values = canonical_row(
            normalized,
            original_record,
            source_context,
            source_year,
            source_sha256,
        )

        market = cast(str, values[_MARKET_INDEX])
        self.metrics.market_counts[market] = (
            self.metrics.market_counts.get(market, 0) + 1
        )
        if market not in _KNOWN_TPMERC_CODES:
            self.metrics.unknown_market_counts[market] = (
                self.metrics.unknown_market_counts.get(market, 0) + 1
            )
        if source_year is not None:
            trading_year = cast(str, values[_TRADING_DATE_INDEX])[:4]
            if trading_year != f'{source_year:04d}':
                raise field_error(
                    context,
                    'data_pregao',
                    normalized[2:10],
                    f'Trading date year {int(trading_year)} does not match '
                    f'source year {source_year}',
                )

        return self._select_quote(
            values, market, target_tpmerc_codes, all_markets
        )

    def _select_quote(
        self,
        values: CsvRow,
        market: str,
        target_tpmerc_codes: set[str],
        all_markets: bool,
    ) -> CsvRow | None:
        """Count the selection outcome and preserve canonical field order."""
        if not all_markets and market not in target_tpmerc_codes:
            self.metrics.filtered_records += 1
            return None
        self.metrics.selected_records += 1
        self.metrics.parsed_records += 1
        return values

    @staticmethod
    def _record_error(
        context: B3RecordContext | None,
        line: str,
        record_type: str,
        field_name: str,
        raw_value: str,
        cause: Exception | str,
    ) -> ExtractionError:
        """Create full source context only for a rejected record."""
        record_context = context or B3RecordContext(
            source_basename='<memory>',
            zip_member='',
            physical_line=0,
            logical_record=0,
            record_type=record_type,
            raw_preview=line[:80],
        )
        return record_context.with_field(
            field_name, raw_value
        ).extraction_error(cause)


def _remove_one_line_terminator(line: str) -> str:
    """Remove one physical LF, CRLF, or CR terminator only."""
    return line.removesuffix('\r\n').removesuffix('\n').removesuffix('\r')
