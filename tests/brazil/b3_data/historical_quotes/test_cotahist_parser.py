"""Strict fixed-width COTAHIST parsing regressions."""

from datetime import date
from decimal import Decimal

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import CotahistParserB3
from globaldatafinance.brazil.b3_data.historical_quotes.integrity import (
    B3RecordContext,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record

pytestmark = pytest.mark.unit


def _replace(record: str, start: int, end: int, value: str) -> str:
    """Replace one fixed-width field while preserving the source length."""
    assert len(value) <= end - start
    return record[:start] + value.ljust(end - start) + record[end:]


def test_parser_emits_all_typed_fields_and_precise_decimals() -> None:
    """A selected financial line becomes exactly one typed B3 record."""
    parser = CotahistParserB3()

    record = parser.parse_line(build_cotahist_record(), {'010'})

    assert record is not None
    assert record['data_pregao'] == date(2024, 1, 15)
    assert record['ticker'] == 'PETR4'
    assert record['tipo_mercado'] == '010'
    assert record['preco_fechamento'] == Decimal('123.45')
    assert record['preco_fechamento'].as_tuple() == (
        Decimal('123.45').as_tuple()
    )
    assert record['numero_negocios'] == 1
    assert parser.metrics.selected_records == 1
    assert parser.metrics.parsed_records == 1


def test_arrow_csv_row_preserves_the_same_strict_typed_values() -> None:
    """The production fast path must remain equivalent to ``parse_line``."""
    source = build_cotahist_record()
    typed = CotahistParserB3().parse_line(source, {'010'})
    parser = CotahistParserB3()

    row = parser.parse_line_to_csv_row(source, {'010'})

    assert row is not None
    assert row[0] == '2024-01-15'
    assert row[10] == '123.45'
    assert row[16] == '2024-12-31'
    assert CotahistParserB3._typed_record(row) == typed
    assert (
        parser.metrics.selected_records == parser.metrics.parsed_records == 1
    )


def test_controls_and_blank_lines_are_counted_without_persisting() -> None:
    """Official controls and blanks are not financial records."""
    parser = CotahistParserB3()

    assert parser.parse_line('', {'010'}) is None
    assert parser.parse_line('00HEADER', {'010'}) is None
    assert parser.parse_line('99TRAILER', {'010'}) is None

    assert parser.metrics.blank_lines == 1
    assert parser.metrics.header_records == 1
    assert parser.metrics.trailer_records == 1
    assert parser.metrics.selected_records == 0


def test_filtering_happens_before_strict_field_conversion() -> None:
    """A non-selected market may contain irrelevant malformed fields."""
    malformed = _replace(build_cotahist_record(market='070'), 56, 69, 'bad')
    parser = CotahistParserB3()

    assert parser.parse_line(malformed, {'010'}) is None
    assert parser.metrics.filtered_records == 1
    assert parser.metrics.selected_records == 0


@pytest.mark.parametrize('length', [244, 246])
def test_selected_record_requires_exact_245_character_width(
    length: int,
) -> None:
    """Selected records are never padded or truncated silently."""
    parser = CotahistParserB3()
    record = build_cotahist_record()
    candidate = record[:length] if length < 245 else record + 'X'

    with pytest.raises(ExtractionError, match='Expected exactly 245'):
        parser.parse_line(candidate, {'010'})


@pytest.mark.parametrize(
    ('start', 'end', 'value', 'field_name'),
    [
        (2, 10, '20241340', 'data_pregao'),
        (12, 24, '', 'ticker'),
        (56, 69, 'not-a-number', 'preco_abertura'),
        (147, 152, '', 'numero_negocios'),
    ],
)
def test_invalid_selected_field_has_contextual_extraction_error(
    start: int, end: int, value: str, field_name: str
) -> None:
    """Strict failures identify the source field instead of defaults."""
    parser = CotahistParserB3()
    record = _replace(build_cotahist_record(), start, end, value)
    context = B3RecordContext(
        source_basename='COTAHIST_A2024.TXT',
        zip_member='COTAHIST_A2024.TXT',
        physical_line=17,
        logical_record=17,
    )

    with pytest.raises(ExtractionError, match=f'field={field_name}'):
        parser.parse_line(record, {'010'}, context=context)


def test_unknown_nonempty_record_type_fails_atomically() -> None:
    """Unknown source records are not silently dropped."""
    parser = CotahistParserB3()

    with pytest.raises(ExtractionError, match='record_type'):
        parser.parse_line('05UNKNOWN', {'010'})


def test_optional_expiry_date_accepts_only_blank_or_zero_sentinel() -> None:
    """A blank expiry is null, whereas an invalid one raises an error."""
    parser = CotahistParserB3()
    blank_expiry = _replace(build_cotahist_record(), 202, 210, '')

    result = parser.parse_line(blank_expiry, {'010'})
    assert result is not None
    assert result['data_vencimento'] is None

    invalid_expiry = _replace(build_cotahist_record(), 202, 210, '20240230')
    with pytest.raises(ExtractionError, match='data_vencimento'):
        parser.parse_line(invalid_expiry, {'010'})


def test_numeric_normalizers_do_not_round_or_default() -> None:
    """Production numeric normalizers reject values outside persisted types."""
    context = B3RecordContext('source', 'member', 1, 1)

    assert (
        CotahistParserB3._normalize_decimal_v99('12345', context) == '123.45'
    )
    with pytest.raises(ExtractionError, match='decimal128'):
        CotahistParserB3._normalize_decimal_v99('9' * 39, context)
    with pytest.raises(ExtractionError, match='decimal128'):
        CotahistParserB3._normalize_decimal_v99('9' * 37, context)
    with pytest.raises(ExtractionError, match='int64'):
        CotahistParserB3._normalize_int(str(2**63), context)


def test_non_ascii_numeric_glyphs_fail_with_field_context() -> None:
    """A Latin-1 digit-like glyph is not a valid financial numeric value."""
    parser = CotahistParserB3()
    record = _replace(build_cotahist_record(), 56, 69, '²')

    with pytest.raises(ExtractionError, match='field=preco_abertura'):
        parser.parse_line_to_csv_row(record, {'010'})
