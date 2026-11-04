"""Strict fixed-width COTAHIST parsing regressions."""

from datetime import date
from decimal import Decimal

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    cotahist_parser,
)
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
    assert record['prazo_termo'] == ''
    assert record['moeda_referencia'] == ''
    assert record['preco_exercicio'] == Decimal('0.00')
    assert record['indicador_correcao'] == '0'
    assert record['preco_exercicio_pontos'] == Decimal('0.000000')
    assert record['registro_original'] == build_cotahist_record().encode(
        'latin-1'
    )
    assert parser.metrics.selected_records == 1
    assert parser.metrics.parsed_records == 1


@pytest.mark.parametrize('digit', ['0', '9'])
def test_full_width_numeric_extremes_preserve_exact_values(digit: str) -> None:
    """Every numeric quotation field accepts its full official width."""
    source = build_cotahist_record()
    expected: dict[str, object] = {}
    for name, start, stop, scale in [
        ('preco_abertura', 56, 69, 2),
        ('preco_maximo', 69, 82, 2),
        ('preco_minimo', 82, 95, 2),
        ('preco_medio', 95, 108, 2),
        ('preco_fechamento', 108, 121, 2),
        ('melhor_oferta_compra', 121, 134, 2),
        ('melhor_oferta_venda', 134, 147, 2),
        ('numero_negocios', 147, 152, 0),
        ('quantidade_total', 152, 170, 0),
        ('volume_total', 170, 188, 2),
        ('preco_exercicio', 188, 201, 2),
        ('fator_cotacao', 210, 217, 0),
        ('preco_exercicio_pontos', 217, 230, 6),
        ('numero_distribuicao', 242, 245, 0),
    ]:
        digits = digit * (stop - start)
        source = _replace(source, start, stop, digits)
        expected[name] = (
            Decimal(f'{digits[:-scale]}.{digits[-scale:]}')
            if scale
            else int(digits)
        )
    source = _replace(source, 201, 202, digit)

    record = CotahistParserB3().parse_line(source, set(), all_markets=True)

    assert record is not None
    assert {name: record[name] for name in expected} == expected
    assert record['indicador_correcao'] == digit
    assert record['registro_original'] == source.encode('latin-1')


@pytest.mark.parametrize('sentinel', ['        ', '00000000', '99991231'])
def test_expiry_sentinels_and_far_future_date_are_explicit(
    sentinel: str,
) -> None:
    """Only documented absent dates become null; valid future dates persist."""
    source = _replace(build_cotahist_record(), 202, 210, sentinel)
    record = CotahistParserB3().parse_line(source, {'010'})

    assert record is not None
    assert record['data_vencimento'] == (
        date(9999, 12, 31) if sentinel == '99991231' else None
    )


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
    assert cotahist_parser.field_conversion.typed_record(row) == typed
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


def test_filtering_happens_after_strict_field_conversion() -> None:
    """A malformed quotation fails even when its market is excluded."""
    malformed = _replace(build_cotahist_record(market='070'), 56, 69, 'bad')
    parser = CotahistParserB3()

    with pytest.raises(ExtractionError, match='preco_abertura'):
        parser.parse_line(malformed, {'010'})
    assert parser.metrics.filtered_records == 0
    assert parser.metrics.selected_records == 0


@pytest.mark.parametrize('market', ['   ', 'A10', '01 '])
def test_invalid_market_code_is_rejected_even_for_filtered_records(
    market: str,
) -> None:
    """TPMERC must be exactly three ASCII digits before selection."""
    malformed = _replace(build_cotahist_record(), 24, 27, market)

    with pytest.raises(ExtractionError, match='tipo_mercado'):
        CotahistParserB3().parse_line(malformed, {'010'})


def test_complete_selection_preserves_unknown_codes_and_coordinates() -> None:
    """Complete selection keeps unknown codes and the original source bytes."""
    source = build_cotahist_record(market='999')
    context = B3RecordContext(
        source_basename='COTAHIST_A2024.TXT',
        zip_member='',
        physical_line=9,
        logical_record=8,
    )
    parser = CotahistParserB3()

    result = parser.parse_line(
        source,
        set(),
        context=context,
        all_markets=True,
        source_year=2024,
        source_sha256='a' * 64,
    )

    assert result is not None
    assert result['tipo_mercado'] == '999'
    assert result['id_fonte'] == 'a' * 64
    assert result['arquivo_origem'] == 'COTAHIST_A2024.TXT'
    assert result['membro_origem'] == ''
    assert result['ano_origem'] == 2024
    assert result['linha_origem'] == 9
    assert result['registro_original'] == source.encode('latin-1')
    assert parser.metrics.unknown_market_counts == {'999': 1}


def test_complete_selection_requires_source_trading_year() -> None:
    """A quote cannot be attributed to an annual source from another year."""
    with pytest.raises(ExtractionError, match='source year 2025'):
        CotahistParserB3().parse_line(
            build_cotahist_record(year=2024),
            set(),
            all_markets=True,
            source_year=2025,
        )


@pytest.mark.parametrize(
    ('start', 'end', 'value', 'expected'),
    [
        (188, 201, '0000000012345', Decimal('123.45')),
        (217, 230, '0000012345678', Decimal('12.345678')),
    ],
)
def test_new_implied_decimal_fields_keep_their_declared_scale(
    start: int, end: int, value: str, expected: Decimal
) -> None:
    """Scale two and scale six source values are represented exactly."""
    source = _replace(build_cotahist_record(), start, end, value)

    result = CotahistParserB3().parse_line(source, {'010'})

    assert result is not None
    field_name = (
        'preco_exercicio' if start == 188 else 'preco_exercicio_pontos'
    )
    assert result[field_name] == expected


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
        cotahist_parser.field_conversion.normalize_decimal('12345', 2, context)
        == '123.45'
    )
    with pytest.raises(ExtractionError, match='decimal128'):
        cotahist_parser.field_conversion.normalize_decimal(
            '9' * 39, 2, context
        )
    with pytest.raises(ExtractionError, match='decimal128'):
        cotahist_parser.field_conversion.normalize_decimal(
            '9' * 37, 2, context
        )
    with pytest.raises(ExtractionError, match='int64'):
        cotahist_parser.field_conversion.normalize_int(str(2**63), context)


def test_non_ascii_numeric_glyphs_fail_with_field_context() -> None:
    """A Latin-1 digit-like glyph is not a valid financial numeric value."""
    parser = CotahistParserB3()
    record = _replace(build_cotahist_record(), 56, 69, '²')

    with pytest.raises(ExtractionError, match='field=preco_abertura'):
        parser.parse_line_to_csv_row(record, {'010'})
