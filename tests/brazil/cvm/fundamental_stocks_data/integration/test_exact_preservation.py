"""Regressions for exact CVM field and source archive preservation."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    'value',
    [
        '000012345',
        '-0',
        '1.23456789012345678901234567890123456789',
        '9007199254740993.0',
        '1e-400',
        '1e400',
        '0.00',
        '+1.50e+02',
        'N/A',
        'n/a',
        'NULL',
        'NaN',
        'None',
        '',
        'TrUe',
        ' 123 ',
        '\x00control',
    ],
)
def test_every_source_token_survives_exactly(
    tmp_path: Path, value: str
) -> None:
    """Numeric-looking values and null-like literals remain exact text."""
    source = tmp_path / 'source.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('source.csv', f'value\n{value}\n'.encode())

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    table = pq.read_table(tmp_path / 'source.parquet')
    assert table.column('value').to_pylist() == [value]
    assert table.schema.field('value').type == pa.string()
    assert table.column('value').null_count == 0


def test_success_preserves_all_original_archive_members(
    tmp_path: Path,
) -> None:
    """CSV conversion keeps original CSV bytes and non-CSV attachments."""
    source = tmp_path / 'dfp_cia_aberta_2024.zip'
    members = {
        'nested/data.csv': b'id;value\n0001;1.234567890123456789\n',
        'attachment.pdf': b'original attachment',
        'dictionary.txt': b'original dictionary',
    }
    with zipfile.ZipFile(source, 'w') as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    original_bytes = source.read_bytes()

    result = download_extraction.extract_downloaded_file(
        ParquetExtractorAdapterCVM(),
        str(source),
        str(tmp_path),
        'DFP',
        '2024',
    )

    assert result is None
    assert source.read_bytes() == original_bytes
    with zipfile.ZipFile(source) as archive:
        assert {name: archive.read(name) for name in archive.namelist()} == (
            members
        )
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '0001', 'value': '1.234567890123456789'}
    ]


def test_ipe_download_includes_all_historical_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The facade accepts the official IPE history starting in 2003."""
    client = FundamentalStocksDataCVM()
    captured: list[tuple[str, str, str, str]] = []

    def capture_downloads(tasks, *, automatic_extractor):
        from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
            DownloadResultCVM,
        )

        assert automatic_extractor is False
        captured.extend(tasks)
        return DownloadResultCVM()

    monkeypatch.setattr(
        client.download_adapter, 'download_docs', capture_downloads
    )
    client.download(
        str(tmp_path / 'output'),
        list_docs=['IPE', 'DFP'],
        initial_year=2003,
        last_year=2010,
    )

    assert sorted((doc, year) for _, doc, year, _ in captured) == [
        ('DFP', '2010'),
        *(('IPE', str(year)) for year in range(2003, 2011)),
    ]
    assert not (tmp_path / 'output' / 'DFP' / '2003').exists()
