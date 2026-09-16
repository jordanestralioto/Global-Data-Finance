"""Property-based invariants for strict B3 COTAHIST parsing."""

from __future__ import annotations

from decimal import Decimal

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import CotahistParserB3
from tests.support.builders import build_cotahist_record

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ModuleNotFoundError:
    pytest.skip(
        'hypothesis is installed through the development dependency group',
        allow_module_level=True,
    )

pytestmark = pytest.mark.unit

_TICKER_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def _replace(record: str, start: int, end: int, value: str) -> str:
    """Replace one fixed-width field without changing the record length."""
    return record[:start] + value.ljust(end - start) + record[end:]


@settings(max_examples=80, deadline=None)
@given(
    ticker=st.text(
        alphabet=_TICKER_ALPHABET,
        min_size=1,
        max_size=12,
    ),
    year=st.integers(min_value=2000, max_value=9999),
)
def test_valid_serialized_records_round_trip_through_the_strict_parser(
    ticker: str,
    year: int,
) -> None:
    """A valid serialized record preserves its selected identifier and date."""
    record = build_cotahist_record(ticker=ticker, year=year)
    parsed = CotahistParserB3().parse_line(record, {'010'})

    assert parsed is not None
    assert parsed['ticker'] == ticker
    assert parsed['tipo_mercado'] == '010'
    assert parsed['data_pregao'].year == year


@settings(max_examples=80, deadline=None)
@given(value=st.integers(min_value=0, max_value=10**13 - 1))
def test_v99_decimal_preserves_exact_decimal_scale_and_digits(
    value: int,
) -> None:
    """V99 parsing never rounds cents while converting fixed-width digits."""
    raw_value = str(value).zfill(13)
    record = _replace(build_cotahist_record(), 56, 69, raw_value)
    parsed = CotahistParserB3().parse_line(record, {'010'})
    expected = Decimal((0, Decimal(str(value)).as_tuple().digits, -2))

    assert parsed is not None
    assert parsed['preco_abertura'] == expected
    assert parsed['preco_abertura'].as_tuple() == expected.as_tuple()
