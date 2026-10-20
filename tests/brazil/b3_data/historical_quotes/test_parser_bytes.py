"""Byte and string parsing share strict validation and selection semantics."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.integrity import (
    B3RecordContext,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record, write_cotahist_txt


def _variant_line(variant: str) -> str:
    """Build independent input variations without changing parser state."""
    line = build_cotahist_record()
    filtered = build_cotahist_record(market='070')
    return {
        'valid': line,
        'latin1': line[:27] + 'AÇÃO ÁGUA'.ljust(12) + line[39:],
        'invalid_date': line[:2] + '20240230' + line[10:],
        'year': build_cotahist_record(year=2023),
        'filtered': filtered,
        'filtered_corrupt': filtered[:56] + 'X' * 13 + filtered[69:],
        'unknown': build_cotahist_record(market='999'),
        'blank': '',
        'header': '00' + line[2:],
        'trailer': '99' + line[2:],
        'unsupported': '02' + line[2:],
        'width': line[:-1],
    }[variant]


@pytest.mark.unit
@pytest.mark.parametrize(
    'variant',
    [
        'valid',
        'latin1',
        'invalid_date',
        'year',
        'filtered',
        'filtered_corrupt',
        'unknown',
        'blank',
        'header',
        'trailer',
        'unsupported',
        'width',
    ],
)
@pytest.mark.parametrize('terminator', ['', '\n', '\r\n', '\r'])
def test_bytes_and_string_parsers_agree_on_rows_errors_and_metrics(
    variant: str, terminator: str
) -> None:
    """All source fields are checked before filtering on either entrypoint."""
    line = _variant_line(variant) + terminator
    text_parser, byte_parser = CotahistParserB3(), CotahistParserB3()
    context = B3RecordContext('COTAHIST_A2024.TXT', '', 2, 2)
    options: dict[str, Any] = {
        'context': context,
        'source_year': 2024,
        'source_sha256': 'a' * 64,
    }
    try:
        expected = text_parser.parse_line_to_csv_row(line, {'010'}, **options)
    except ExtractionError as expected_error:
        with pytest.raises(ExtractionError) as observed:
            byte_parser._parse_bytes_to_csv_row(
                line.encode('latin-1'), {'010'}, **options
            )
        assert str(observed.value) == str(expected_error)
    else:
        actual = byte_parser._parse_bytes_to_csv_row(
            line.encode('latin-1'), {'010'}, **options
        )
        assert actual == expected
        if actual is not None:
            assert actual[-1] == line.removesuffix('\r\n').removesuffix(
                '\n'
            ).removesuffix('\r').encode('latin-1')
    assert byte_parser.metrics == text_parser.metrics


@pytest.mark.integration
@pytest.mark.parametrize('quotes_only', [False, True])
def test_source_date_bounds_include_valid_filtered_quotes(
    tmp_path: Path, quotes_only: bool
) -> None:
    """Final date conversion preserves bounds outside the selected market."""
    records = []
    for day, market in [
        ('20241231', '070'),
        ('20240615', '010'),
        ('20240101', '070'),
    ]:
        record = build_cotahist_record(market=market)
        records.append(record[:2] + day + record[10:])
    path = write_cotahist_txt(tmp_path, year=2024, records=records)
    if quotes_only:
        content = path.read_bytes()
        path.write_bytes(content.replace(b'00000000005', b'00000000003'))
    source = resolve_cotahist_sources(
        tmp_path, target_tpmerc_codes={'010'}, all_markets=False
    ).sources[0]
    assert source.selected_quotes == 1
    assert source.intentional_exclusions == 2
    assert source.first_trading_date == date(2024, 1, 1)
    assert source.last_trading_date == date(2024, 12, 31)
    assert source.trailer_convention == (
        'quotes_only' if quotes_only else 'quotes_and_controls'
    )
