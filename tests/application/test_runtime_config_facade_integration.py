"""Integration tests for runtime configuration snapshots across facades."""

from __future__ import annotations

from pathlib import Path

import pytest

from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
from globaldatafinance.core.config import (
    ArchiveSafetySettings,
    NetworkSettings,
    PathSafetySettings,
    Settings,
)
from globaldatafinance.macro_exceptions import CorruptedZipError, SecurityError
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_zip,
    write_zip,
)

pytestmark = pytest.mark.integration


def test_cvm_facades_hold_independent_network_and_archive_snapshots(
    tmp_path: Path,
) -> None:
    """CVM facades hold distinct snapshots and enforce independent limits."""
    settings_a = Settings(
        network=NetworkSettings(timeout=30),
        archive=ArchiveSafetySettings(max_archive_bytes=50),
    )
    settings_b = Settings(
        network=NetworkSettings(timeout=120),
        archive=ArchiveSafetySettings(max_archive_bytes=10_000_000),
    )

    client_a = FundamentalStocksDataCVM(settings=settings_a)
    client_b = FundamentalStocksDataCVM(settings=settings_b)

    assert client_a.settings.network.timeout == 30
    assert client_b.settings.network.timeout == 120
    assert client_a.download_adapter.requests_adapter.timeout == 30
    assert client_b.download_adapter.requests_adapter.timeout == 120

    zip_file = write_zip(
        tmp_path / 'sample.zip',
        {'data.csv': 'col1;col2\nval1;val2\n'},
    )
    dest_a = tmp_path / 'extract_a'
    dest_b = tmp_path / 'extract_b'
    dest_a.mkdir()
    dest_b.mkdir()

    with pytest.raises(CorruptedZipError):
        client_a.download_adapter._get_file_extractor().extract(
            str(zip_file), str(dest_a)
        )

    client_b.download_adapter._get_file_extractor().extract(
        str(zip_file), str(dest_b)
    )
    assert (dest_b / 'data.parquet').exists()


def test_cvm_facades_enforce_independent_unc_path_safety() -> None:
    """CVM destination validation respects the caller-injected UNC roots."""
    client_a = FundamentalStocksDataCVM(
        settings=Settings(
            path_safety=PathSafetySettings(
                allowed_unc_roots=(r'\\fileserver\cvm_team_a',)
            )
        )
    )
    client_b = FundamentalStocksDataCVM(
        settings=Settings(
            path_safety=PathSafetySettings(
                allowed_unc_roots=(r'\\fileserver\cvm_team_b',)
            )
        )
    )

    with pytest.raises(SecurityError):
        client_a.download(
            destination_path=r'\\fileserver\cvm_team_b\output',
            list_docs=['DFP'],
            initial_year=2023,
            last_year=2023,
        )

    with pytest.raises(SecurityError):
        client_b.download(
            destination_path=r'\\fileserver\cvm_team_a\output',
            list_docs=['DFP'],
            initial_year=2023,
            last_year=2023,
        )


def test_b3_facades_hold_independent_archive_safety_limits(
    tmp_path: Path,
) -> None:
    """B3 extraction respects caller-injected archive limits independently."""
    input_dir = tmp_path / 'cotahist'
    input_dir.mkdir()
    write_cotahist_zip(
        input_dir,
        year=2024,
        records=[build_cotahist_record(ticker='VALE3')],
    )

    client_strict = HistoricalQuotesB3(
        settings=Settings(archive=ArchiveSafetySettings(max_archive_bytes=50))
    )
    client_standard = HistoricalQuotesB3(
        settings=Settings(
            archive=ArchiveSafetySettings(max_archive_bytes=10_000_000)
        )
    )

    strict_out = tmp_path / 'strict_out'
    res_strict = client_strict.extract(
        path_of_docs=str(input_dir),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(strict_out),
        output_filename='strict_quotes',
        verbose=False,
    )
    assert res_strict['success'] is False
    assert res_strict['error_count'] == 1
    assert any(
        'CorruptedZipError' in err for err in res_strict['errors'].values()
    )

    standard_out = tmp_path / 'standard_out'
    res_standard = client_standard.extract(
        path_of_docs=str(input_dir),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(standard_out),
        output_filename='standard_quotes',
        verbose=False,
    )
    assert res_standard['success'] is True
    assert res_standard['total_records'] == 1


def test_b3_facades_enforce_independent_unc_path_safety(
    tmp_path: Path,
) -> None:
    """B3 destination verification honors caller-injected UNC roots."""
    input_dir = tmp_path / 'cotahist_input'
    input_dir.mkdir()

    client_a = HistoricalQuotesB3(
        settings=Settings(
            path_safety=PathSafetySettings(
                allowed_unc_roots=(r'\\storage\share_a',)
            )
        )
    )
    client_b = HistoricalQuotesB3(
        settings=Settings(
            path_safety=PathSafetySettings(
                allowed_unc_roots=(r'\\storage\share_b',)
            )
        )
    )

    with pytest.raises(SecurityError):
        client_a.extract(
            path_of_docs=str(input_dir),
            assets_list=['ações'],
            initial_year=2024,
            last_year=2024,
            destination_path=r'\\storage\share_b\quotes',
            verbose=False,
        )

    with pytest.raises(SecurityError):
        client_b.extract(
            path_of_docs=str(input_dir),
            assets_list=['ações'],
            initial_year=2024,
            last_year=2024,
            destination_path=r'\\storage\share_a\quotes',
            verbose=False,
        )
