"""Full COTAHIST source-document validation regressions."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


def _replace(record: str, start: int, stop: int, value: str) -> str:
    """Replace one fixed-width field while keeping the record width."""
    return record[:start] + value.ljust(stop - start) + record[stop:]


def test_preflight_reports_source_hashes_controls_counts_and_dates(
    tmp_path: Path,
) -> None:
    """Validated facts bind the original input and full uncompressed stream."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
        generation_date=date(2025, 1, 2),
    )
    payload = source.read_bytes()

    resolution = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes={'010'},
        all_markets=False,
    )

    result = resolution.sources[0]
    assert result.outer_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.content_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.year == 2024
    assert result.member == ''
    assert result.raw_quotes == result.selected_quotes == 1
    assert result.intentional_exclusions == 0
    assert result.declared_records == 3
    assert result.trailer_convention == 'quotes_and_controls'
    assert result.generation_date == date(2025, 1, 2)
    assert (
        result.first_trading_date
        == result.last_trading_date
        == date(2024, 1, 15)
    )
    assert result.header_bytes[:2] == b'00'
    assert result.trailer_bytes[:2] == b'99'


def test_preflight_accepts_quotes_only_trailer_with_a_warning(
    tmp_path: Path,
) -> None:
    """The second observed trailer convention is explicit in the report."""
    write_cotahist_txt(
        tmp_path,
        year=2025,
        records=[build_cotahist_record(year=2025)],
        trailer_convention='quotes_only',
    )

    resolution = resolve_cotahist_sources(
        tmp_path,
        expected_years={2025},
        target_tpmerc_codes={'010'},
        all_markets=False,
    )

    result = resolution.sources[0]
    assert result.trailer_convention == 'quotes_only'
    assert [warning.code for warning in result.warnings] == [
        'TRAILER_QUOTES_ONLY'
    ]


def test_preflight_rejects_every_other_trailer_total(tmp_path: Path) -> None:
    """Trailer totals must match one of the two accepted conventions."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    lines = source.read_text(encoding='latin-1').splitlines()
    lines[-1] = lines[-1][:31] + '00000000007' + lines[-1][42:]
    source.write_bytes(('\n'.join(lines) + '\n').encode('latin-1'))

    with pytest.raises(CotahistCatalogError, match='unsupported record total'):
        resolve_cotahist_sources(
            tmp_path,
            expected_years={2024},
            target_tpmerc_codes={'010'},
            all_markets=False,
        )


def test_preflight_validates_fields_in_intentionally_filtered_markets(
    tmp_path: Path,
) -> None:
    """A corrupted quotation fails before market selection can exclude it."""
    invalid = _replace(
        build_cotahist_record(year=2024, market='070'),
        56,
        69,
        'not-a-number',
    )
    write_cotahist_txt(tmp_path, year=2024, records=[invalid])

    with pytest.raises(CotahistCatalogError, match='preco_abertura'):
        resolve_cotahist_sources(
            tmp_path,
            expected_years={2024},
            target_tpmerc_codes={'010'},
            all_markets=False,
        )


def test_preflight_rejects_quote_year_mismatch(tmp_path: Path) -> None:
    """Every quotation date must belong to its external annual file."""
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2023)],
    )

    with pytest.raises(
        CotahistCatalogError, match='does not match source year'
    ):
        resolve_cotahist_sources(
            tmp_path,
            expected_years={2024},
            target_tpmerc_codes={'010'},
            all_markets=False,
        )


def test_preflight_preserves_unknown_numeric_market_and_counts_it(
    tmp_path: Path,
) -> None:
    """Unknown three-digit markets remain selected by complete extraction."""
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, market='999')],
    )

    resolution = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes=set(),
        all_markets=True,
    )

    result = resolution.sources[0]
    assert result.market_counts == (('999', 1),)
    assert result.unknown_market_counts == (('999', 1),)
    assert result.selected_quotes == 1
    assert result.intentional_exclusions == 0
    assert any(warning.code == 'UNKNOWN_TPMERC' for warning in result.warnings)


def test_preflight_reports_missing_years_without_creating_outputs(
    tmp_path: Path,
) -> None:
    """Catalog resolution keeps annual gaps as explicit coverage facts."""
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )

    resolution = resolve_cotahist_sources(
        tmp_path,
        expected_years={2023, 2024},
        target_tpmerc_codes={'010'},
        all_markets=False,
    )

    assert resolution.missing_years == (2023,)
    assert [source.year for source in resolution.sources] == [2024]


def test_identical_zip_and_txt_sources_select_zip_and_report_duplicate(
    tmp_path: Path,
) -> None:
    """An identical annual TXT is validated and explicitly ignored."""
    records = [build_cotahist_record(year=2024)]
    zip_path = write_cotahist_zip(tmp_path, year=2024, records=records)
    txt_path = write_cotahist_txt(tmp_path, year=2024, records=records)

    resolution = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes={'010'},
        all_markets=False,
    )

    assert [source.path for source in resolution.sources] == [zip_path]
    assert resolution.ignored_duplicate_sources == (str(txt_path),)


def test_different_zip_and_txt_sources_fail_as_conflicting_inputs(
    tmp_path: Path,
) -> None:
    """Two independently valid but different annual streams cannot coexist."""
    write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='VALE3')],
    )

    with pytest.raises(CotahistCatalogError, match='Conflicting ZIP and TXT'):
        resolve_cotahist_sources(
            tmp_path,
            expected_years={2024},
            target_tpmerc_codes={'010'},
            all_markets=False,
        )


def test_preflight_rejects_wrong_control_origin_and_record_order(
    tmp_path: Path,
) -> None:
    """Control identity and header/quote/trailer order are mandatory."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    lines = source.read_text(encoding='latin-1').splitlines()
    lines[0] = _replace(lines[0], 15, 23, 'INVALID')
    source.write_bytes(('\n'.join(lines) + '\n').encode('latin-1'))

    with pytest.raises(CotahistCatalogError, match='control_origin'):
        resolve_cotahist_sources(
            tmp_path,
            expected_years={2024},
            target_tpmerc_codes={'010'},
            all_markets=False,
        )
