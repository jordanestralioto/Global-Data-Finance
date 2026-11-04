"""Independent CVM families reuse preservation without company selection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.ingestion.extract import CvmParquetExtractor
from globaldatafinance.brazil.cvm.ingestion.http import CvmDownloadAdapter
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.fake_http import install_mock_http_transport

pytestmark = pytest.mark.integration


def _write_owned_output(path: Path, source: Path) -> bytes:
    table = pa.table({'id': ['obsolete']}).replace_schema_metadata(
        {b'cvm.source-archive': source.name.encode('utf-8')}
    )
    pq.write_table(table, path)
    return path.read_bytes()


def _write_archive(path: Path) -> bytes:
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(
            'funds.csv',
            b'FUND_ID;REFERENCE_DATE;VALUE\r\n'
            b'00001;1999-01-31;1.234,5600\r\n00002;;N/A\r\n',
        )
        archive.writestr('details.csv', b'NOTE;VALUE\n"literal";\n')
        archive.writestr('attachment.txt', b'retained attachment')
    return path.read_bytes()


def _assert_preserved_funds(destination: Path, archive_name: str) -> None:
    expected = {
        'funds.parquet': [
            {
                'FUND_ID': '00001',
                'REFERENCE_DATE': '1999-01-31',
                'VALUE': '1.234,5600',
            },
            {'FUND_ID': '00002', 'REFERENCE_DATE': '', 'VALUE': 'N/A'},
        ],
        'details.parquet': [{'NOTE': '"literal"', 'VALUE': ''}],
    }
    for name, records in expected.items():
        table = pq.read_table(destination / name)
        assert table.to_pylist() == records
        assert all(field.type == pa.string() for field in table.schema)
        metadata = table.schema.metadata or {}
        assert metadata[b'cvm.contract'] == b'exact-text-v1'
        assert metadata[b'cvm.source-archive'] == archive_name.encode('utf-8')
        assert metadata[b'cvm.source-member'] == name.replace(
            '.parquet', '.csv'
        ).encode('utf-8')


def test_independent_extractor_preserves_all_fields_and_foreign_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'funds_1999.zip'
    original = _write_archive(source)
    foreign = tmp_path / 'other-family.parquet'
    foreign.write_bytes(b'caller-owned data')

    CvmParquetExtractor().extract(str(source), str(tmp_path))

    _assert_preserved_funds(tmp_path, source.name)
    assert source.read_bytes() == original
    assert foreign.read_bytes() == b'caller-owned data'
    assert not (tmp_path / 'attachment.txt').exists()
    assert {path.name for path in tmp_path.glob('*.parquet')} == {
        'funds.parquet',
        'details.parquet',
        'other-family.parquet',
    }


def test_shared_extractor_does_not_infer_company_policy_from_archive_name(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'dfp_cia_aberta_2024.zip'
    original = _write_archive(source)
    foreign = tmp_path / 'dfp_cia_aberta_removed_2024.parquet'
    foreign.write_bytes(b'unidentified caller-owned data')

    CvmParquetExtractor().extract(str(source), str(tmp_path))

    _assert_preserved_funds(tmp_path, source.name)
    assert source.read_bytes() == original
    assert foreign.read_bytes() == b'unidentified caller-owned data'


@pytest.mark.asyncio
@pytest.mark.parametrize('download', [False, True])
async def test_metadata_free_company_output_is_preserved_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    download: bool,
) -> None:
    source = tmp_path / 'dfp_cia_aberta_2023.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr(
            'dfp_cia_aberta_BPA_con_2023.csv',
            b'CD_CVM;VL_CONTA\n00001;1.234,5600\n',
        )
    payload = source.read_bytes()
    destination = tmp_path / 'outputs'
    destination.mkdir()
    unidentified = destination / 'dfp_cia_aberta_DRE_con_2023.parquet'
    pq.write_table(pa.table({'CD_CVM': [1], 'VL_CONTA': [1.0]}), unidentified)
    previous = unidentified.read_bytes()

    if download:
        install_mock_http_transport(
            monkeypatch,
            lambda _request: httpx.Response(200, content=payload),
        )
        result = await CvmDownloadAdapter(
            None, max_retries=0
        ).async_download_docs(
            [
                (
                    'https://example.test/dfp_cia_aberta_2023.zip',
                    'DFP',
                    '2023',
                    str(destination),
                )
            ],
            automatic_extractor=True,
        )
        assert result.successful_downloads == ['DFP_2023']
        assert result.failed_downloads == {}
        assert (destination / source.name).read_bytes() == payload
    else:
        CvmParquetExtractor().extract(str(source), str(destination))

    assert source.read_bytes() == payload
    assert unidentified.read_bytes() == previous
    assert b'cvm.source-archive' not in (
        pq.read_schema(unidentified).metadata or {}
    )
    generated = pq.read_table(
        destination / 'dfp_cia_aberta_BPA_con_2023.parquet'
    )
    assert generated.to_pylist() == [
        {'CD_CVM': '00001', 'VL_CONTA': '1.234,5600'}
    ]
    assert (
        generated.schema.metadata[b'cvm.source-archive']
        == source.name.encode()
    )
    assert generated.schema.metadata[b'cvm.contract'] == b'exact-text-v1'
    assert {path.name for path in destination.glob('*.parquet')} == {
        'dfp_cia_aberta_BPA_con_2023.parquet',
        unidentified.name,
    }


def test_source_identity_rejects_obsolete_outputs_before_direct_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'funds_1999.zip'
    original = _write_archive(source)
    obsolete = tmp_path / 'funds_obsolete_1999.parquet'
    obsolete_bytes = _write_owned_output(obsolete, source)

    with pytest.raises(ExtractionError, match='Obsolete CVM artifacts'):
        CvmParquetExtractor().extract(str(source), str(tmp_path))

    assert source.read_bytes() == original
    assert obsolete.read_bytes() == obsolete_bytes
    assert not (tmp_path / 'funds.parquet').exists()
    assert not (tmp_path / 'details.parquet').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('supplied_extractor', [False, True])
async def test_independent_download_preserves_unregistered_operation_and_year(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supplied_extractor: bool,
) -> None:
    payload = _write_archive(tmp_path / 'fixture.zip')
    destination = tmp_path / 'download'
    destination.mkdir()
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=payload)

    install_mock_http_transport(monkeypatch, respond)
    extractor = CvmParquetExtractor() if supplied_extractor else None
    result = await CvmDownloadAdapter(
        extractor, max_retries=0
    ).async_download_docs(
        [
            (
                'https://example.test/funds_1999.zip',
                'FUNDS_MONTHLY',
                '1999',
                str(destination),
            )
        ],
        automatic_extractor=True,
    )

    assert result.successful_downloads == ['FUNDS_MONTHLY_1999']
    assert result.failed_downloads == {}
    assert requested == ['https://example.test/funds_1999.zip']
    assert (destination / 'funds_1999.zip').read_bytes() == payload
    _assert_preserved_funds(destination, 'funds_1999.zip')


@pytest.mark.asyncio
@pytest.mark.parametrize('supplied_extractor', [False, True])
async def test_source_identity_protects_default_and_supplied_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supplied_extractor: bool,
) -> None:
    payload = _write_archive(tmp_path / 'fixture.zip')
    destination = tmp_path / 'download'
    destination.mkdir()
    obsolete = destination / 'funds_obsolete_1999.parquet'
    obsolete_bytes = _write_owned_output(
        obsolete, destination / 'funds_1999.zip'
    )
    foreign = destination / 'caller.txt'
    foreign.write_bytes(b'foreign data')

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    install_mock_http_transport(monkeypatch, respond)
    extractor = CvmParquetExtractor() if supplied_extractor else None
    downloader = CvmDownloadAdapter(extractor, max_retries=0)
    result = await downloader.async_download_docs(
        [
            (
                'https://example.test/funds_1999.zip',
                'FUNDS_MONTHLY',
                '1999',
                str(destination),
            )
        ],
        automatic_extractor=True,
    )

    assert result.successful_downloads == []
    assert result.error_count_downloads == 1
    assert (
        'Obsolete CVM artifacts'
        in result.failed_downloads['FUNDS_MONTHLY_1999']
    )
    assert obsolete.read_bytes() == obsolete_bytes
    assert foreign.read_bytes() == b'foreign data'
    assert (destination / 'funds_1999.zip').read_bytes() == payload
    assert not (destination / 'funds.parquet').exists()
    assert not (destination / 'details.parquet').exists()
