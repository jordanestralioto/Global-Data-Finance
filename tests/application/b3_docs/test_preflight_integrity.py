"""Failed source preflight retains observations without publishing output."""

from datetime import date
from pathlib import Path

import pytest

from globaldatafinance import HistoricalQuotesB3
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ('assets', 'selected', 'excluded', 'complete', 'codes'),
    [
        (['TODOS'], 1, 0, True, []),
        (['AÇÕES'], 0, 1, False, ['010', '020']),
    ],
)
def test_failed_preflight_preserves_prior_sources_gaps_and_selection(
    tmp_path: Path,
    assets: list[str],
    selected: int,
    excluded: int,
    complete: bool,
    codes: list[str],
) -> None:
    """A later invalid source does not erase earlier verified source facts."""
    source_dir = tmp_path / 'sources'
    source_dir.mkdir()
    valid = write_cotahist_txt(
        source_dir,
        year=2023,
        records=[build_cotahist_record(year=2023, market='070')],
        generation_date=date(2025, 1, 2),
    )
    invalid_record = build_cotahist_record(year=2024)
    invalid_record = invalid_record[:56] + 'X' * 13 + invalid_record[69:]
    invalid = write_cotahist_txt(
        source_dir, year=2024, records=[invalid_record]
    )
    destination = tmp_path / 'output'

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(source_dir),
        assets_list=assets,
        initial_year=2022,
        last_year=2024,
        destination_path=str(destination),
        verbose=False,
    )

    assert result['success'] is False
    assert result['total_files'] == 2
    assert result['success_count'] == result['total_records'] == 0
    assert result['output_file'] == ''
    assert result['error_count'] == 1
    assert set(result['errors']) == {invalid.name}
    assert 'preco_abertura' in result['errors'][invalid.name]
    integrity = result['integrity']
    assert integrity['status'] == 'failed'
    assert integrity['requested_years'] == [2022, 2023, 2024]
    assert integrity['selected_years'] == [2023]
    assert integrity['missing_years'] == [2022]
    assert integrity['complete_market_selection'] is complete
    assert integrity['market_codes'] == codes
    assert integrity['raw_quotes'] == 1
    assert integrity['selected_quotes'] == selected
    assert integrity['intentional_exclusions'] == excluded
    assert integrity['written_rows'] == integrity['verified_rows'] == 0
    assert integrity['selection_complete'] is False
    assert integrity['source_complete'] is False
    assert integrity['output_sha256'] is None
    assert len(integrity['sources']) == 1
    observed = integrity['sources'][0]
    assert observed['source'] == valid.name
    assert observed['uncompressed_bytes'] == valid.stat().st_size
    assert observed['market_counts'] == {'070': 1}
    assert observed['generation_date'] == '2025-01-02'
    assert observed['header_records'] == observed['trailer_records'] == 1
    assert observed['blank_lines'] == 0
    assert observed['warnings'] == []
    assert not destination.exists()


def test_empty_catalog_reports_zero_resolved_files_and_all_missing_years(
    tmp_path: Path,
) -> None:
    """No matching annual source produces no fabricated input count."""
    destination = tmp_path / 'output'

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2023,
        last_year=2024,
        destination_path=str(destination),
        verbose=False,
    )

    assert result['success'] is False
    assert result['total_files'] == result['success_count'] == 0
    assert result['total_records'] == 0
    assert result['integrity']['missing_years'] == [2023, 2024]
    assert result['integrity']['sources'] == []
    assert not destination.exists()
