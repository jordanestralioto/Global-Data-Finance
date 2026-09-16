"""Strict parser for B3 COTAHIST fixed-width quote records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from ....macro_exceptions import ExtractionError
from .integrity import B3RecordContext

_EXPECTED_LENGTH = 245
# ``decimal128(38, 2)`` has 38 total significant digits, two of which are
# reserved for the fractional scale.  COTAHIST V99 values are integer cents,
# so at most 36 digits may appear before the implicit decimal point.
_DECIMAL_MAX_INTEGER_DIGITS = 36
_MAX_INT64_TEXT = str(2**63 - 1)


@dataclass
class B3ParserMetrics:
    """Per-source classification counts produced by the strict parser."""

    blank_lines: int = 0
    header_records: int = 0
    trailer_records: int = 0
    filtered_records: int = 0
    selected_records: int = 0
    parsed_records: int = 0


CsvRow = tuple[str | None, ...]

_FIELD_NAMES = (
    'data_pregao',
    'codigo_bdi',
    'ticker',
    'tipo_mercado',
    'nome_resumido',
    'especificacao_papel',
    'preco_abertura',
    'preco_maximo',
    'preco_minimo',
    'preco_medio',
    'preco_fechamento',
    'melhor_oferta_compra',
    'melhor_oferta_venda',
    'numero_negocios',
    'quantidade_total',
    'volume_total',
    'data_vencimento',
    'fator_cotacao',
    'codigo_isin',
    'numero_distribuicao',
)


class CotahistParserB3:
    """Parse only valid selected COTAHIST records into typed dictionaries."""

    EXPECTED_LINE_LENGTH = _EXPECTED_LENGTH

    def __init__(self) -> None:
        """Initialize source-local classification metrics."""
        self.metrics = B3ParserMetrics()

    @property
    def filtered_records(self) -> int:
        """Return records excluded by TPMERC before field conversion."""
        return self.metrics.filtered_records

    def parse_line(
        self,
        line: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None = None,
    ) -> dict[str, Any] | None:
        """Classify and strictly parse one physical COTAHIST source line."""
        row = self.parse_line_to_csv_row(
            line, target_tpmerc_codes, context=context
        )
        if row is None:
            return None
        return self._typed_record(row)

    def parse_line_to_csv_row(
        self,
        line: str,
        target_tpmerc_codes: set[str],
        context: B3RecordContext | None = None,
    ) -> CsvRow | None:
        """Return a validated canonical row for Arrow CSV conversion.

        This internal fast path validates the same fixed-width record before
        constructing Arrow values.  It avoids creating temporary ``date``,
        ``Decimal``, and dictionary objects that the writer would serialize
        back into CSV immediately afterwards.
        """
        normalized = line.rstrip('\r\n')
        record_type = normalized[:2]
        if not normalized:
            self.metrics.blank_lines += 1
            return None
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
                normalized[:2],
                'Unsupported non-empty COTAHIST record type',
            )
        if len(normalized) != _EXPECTED_LENGTH:
            raise self._record_error(
                context,
                normalized,
                record_type,
                'record_length',
                str(len(normalized)),
                f'Expected exactly {_EXPECTED_LENGTH} characters',
            )
        market = normalized[24:27].strip()
        if market not in target_tpmerc_codes:
            self.metrics.filtered_records += 1
            return None
        self.metrics.selected_records += 1
        row = self._normalize_selected_record(normalized, context)
        self.metrics.parsed_records += 1
        return row

    def _normalize_selected_record(
        self, line: str, context: B3RecordContext | None
    ) -> CsvRow:
        """Normalize the exact COTAHIST layout in canonical schema order."""
        return (
            self._normalize_required_date(
                line[2:10], context, field_name='data_pregao'
            ),
            line[10:12].strip(),
            self._normalize_required_text(
                line[12:24], context, field_name='ticker'
            ),
            self._normalize_required_text(
                line[24:27], context, field_name='tipo_mercado'
            ),
            line[27:39].strip(),
            line[39:49].strip(),
            self._normalize_decimal_v99(
                line[56:69], context, field_name='preco_abertura'
            ),
            self._normalize_decimal_v99(
                line[69:82], context, field_name='preco_maximo'
            ),
            self._normalize_decimal_v99(
                line[82:95], context, field_name='preco_minimo'
            ),
            self._normalize_decimal_v99(
                line[95:108], context, field_name='preco_medio'
            ),
            self._normalize_decimal_v99(
                line[108:121], context, field_name='preco_fechamento'
            ),
            self._normalize_decimal_v99(
                line[121:134], context, field_name='melhor_oferta_compra'
            ),
            self._normalize_decimal_v99(
                line[134:147], context, field_name='melhor_oferta_venda'
            ),
            self._normalize_int(
                line[147:152], context, field_name='numero_negocios'
            ),
            self._normalize_int(
                line[152:170], context, field_name='quantidade_total'
            ),
            self._normalize_decimal_v99(
                line[170:188], context, field_name='volume_total'
            ),
            self._normalize_optional_date(
                line[202:210], context, field_name='data_vencimento'
            ),
            self._normalize_int(
                line[210:217], context, field_name='fator_cotacao'
            ),
            line[230:242].strip(),
            self._normalize_int(
                line[242:245], context, field_name='numero_distribuicao'
            ),
        )

    @staticmethod
    def _typed_record(row: CsvRow) -> dict[str, Any]:
        """Materialize the legacy typed dictionary from canonical values."""
        values: tuple[object, ...] = (
            date.fromisoformat(cast(str, row[0])),
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            Decimal(cast(str, row[6])),
            Decimal(cast(str, row[7])),
            Decimal(cast(str, row[8])),
            Decimal(cast(str, row[9])),
            Decimal(cast(str, row[10])),
            Decimal(cast(str, row[11])),
            Decimal(cast(str, row[12])),
            int(cast(str, row[13])),
            int(cast(str, row[14])),
            Decimal(cast(str, row[15])),
            date.fromisoformat(row[16]) if row[16] is not None else None,
            int(cast(str, row[17])),
            row[18],
            int(cast(str, row[19])),
        )
        return dict(zip(_FIELD_NAMES, values, strict=True))

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

    @staticmethod
    def _field_error(
        context: B3RecordContext | None,
        field_name: str,
        raw_value: str,
        cause: Exception | str,
    ) -> ExtractionError:
        """Build field context only for a rejected value."""
        if context is None:
            context = B3RecordContext('<memory>', '', 0, 0)
        return context.with_field(field_name, raw_value).extraction_error(
            cause
        )

    @staticmethod
    def _normalize_required_date(
        raw_value: str,
        context: B3RecordContext | None = None,
        *,
        field_name: str = 'data_pregao',
    ) -> str:
        """Validate a required date and return its Arrow CSV representation."""
        value = raw_value.strip()
        if (
            len(value) != 8
            or not _is_ascii_digits(value)
            or value == '00000000'
        ):
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'Required date is invalid or empty',
            )
        try:
            date(int(value[:4]), int(value[4:6]), int(value[6:]))
        except ValueError as error:
            raise CotahistParserB3._field_error(
                context, field_name, raw_value, error
            ) from error
        return f'{value[:4]}-{value[4:6]}-{value[6:]}'

    @staticmethod
    def _normalize_optional_date(
        raw_value: str,
        context: B3RecordContext | None = None,
        *,
        field_name: str = 'data_vencimento',
    ) -> str | None:
        """Validate an optional date for Arrow CSV conversion."""
        value = raw_value.strip()
        if not value or value == '00000000':
            return None
        if len(value) != 8 or not _is_ascii_digits(value):
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'Optional date is invalid',
            )
        try:
            date(int(value[:4]), int(value[4:6]), int(value[6:]))
        except ValueError as error:
            raise CotahistParserB3._field_error(
                context, field_name, raw_value, error
            ) from error
        return f'{value[:4]}-{value[4:6]}-{value[6:]}'

    @staticmethod
    def _normalize_decimal_v99(
        raw_value: str,
        context: B3RecordContext | None = None,
        *,
        field_name: str = 'decimal',
    ) -> str:
        """Validate a V99 field without materializing a temporary Decimal."""
        value = raw_value.strip()
        if not value or not _is_ascii_digits(value):
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'Required V99 decimal is empty or non-numeric',
            )
        normalized = value.lstrip('0') or '0'
        if len(normalized) > _DECIMAL_MAX_INTEGER_DIGITS:
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'V99 decimal exceeds decimal128(38, 2)',
            )
        padded = normalized.zfill(3)
        return f'{padded[:-2]}.{padded[-2:]}'

    @staticmethod
    def _normalize_int(
        raw_value: str,
        context: B3RecordContext | None = None,
        *,
        field_name: str = 'integer',
    ) -> str:
        """Validate an int64 field without calling ``int`` on invalid input."""
        value = raw_value.strip()
        if not value or not _is_ascii_digits(value):
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'Required integer is empty or non-numeric',
            )
        normalized = value.lstrip('0') or '0'
        if len(normalized) > len(_MAX_INT64_TEXT) or (
            len(normalized) == len(_MAX_INT64_TEXT)
            and normalized > _MAX_INT64_TEXT
        ):
            raise CotahistParserB3._field_error(
                context, field_name, raw_value, 'Integer exceeds int64'
            )
        return normalized

    @staticmethod
    def _normalize_required_text(
        raw_value: str,
        context: B3RecordContext | None = None,
        *,
        field_name: str,
    ) -> str:
        """Strip a required text field while rejecting an empty value."""
        value = raw_value.strip()
        if not value:
            raise CotahistParserB3._field_error(
                context,
                field_name,
                raw_value,
                'Required text field is empty',
            )
        return value


def _is_ascii_digits(value: str) -> bool:
    """Accept only decimal ASCII digits in fixed-width numeric fields."""
    return value.isascii() and value.isdecimal()
