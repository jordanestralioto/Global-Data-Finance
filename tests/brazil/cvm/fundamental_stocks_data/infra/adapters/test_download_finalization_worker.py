import asyncio
import zipfile
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    DownloadResultCVM,
    destination_io,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_invalid_staged_zip_is_removed_without_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    staging_path = output_dir / 'DFP_2023.zip.part'
    staging_path.write_bytes(b'invalid zip')
    adapter = AsyncDownloadAdapterCVM(file_extractor_repository=MagicMock())

    async def staged_download(_url, _filepath, _doc_name, _year):
        return True, str(staging_path)

    monkeypatch.setattr(adapter, '_download_with_retry', staged_download)
    result = DownloadResultCVM()

    await adapter._download_and_extract(
        'https://example.com/DFP_2023.zip',
        str(output_dir),
        'DFP',
        '2023',
        result,
        MagicMock(),
    )

    assert result.error_count_downloads == 1
    assert 'invalid ZIP' in result.failed_downloads['DFP_2023']
    assert not staging_path.exists()
    assert not (output_dir / 'DFP_2023.zip').exists()


@pytest.mark.asyncio
async def test_failed_zip_promotion_removes_staging_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    staging_path = output_dir / 'DFP_2023.zip.part'
    staging_path.write_bytes(b'validated archive')
    adapter = AsyncDownloadAdapterCVM(file_extractor_repository=MagicMock())
    monkeypatch.setattr(
        adapter,
        '_validate_downloaded_file',
        MagicMock(return_value=True),
    )

    async def staged_download(_url, _filepath, _doc_name, _year):
        return True, str(staging_path)

    def fail_replace(_self, _source, _target):
        raise OSError('promotion failed')

    monkeypatch.setattr(adapter, '_download_with_retry', staged_download)
    monkeypatch.setattr(
        destination_io.DestinationFileOperationsCVM, 'replace', fail_replace
    )
    result = DownloadResultCVM()

    await adapter._download_and_extract(
        'https://example.com/DFP_2023.zip',
        str(output_dir),
        'DFP',
        '2023',
        result,
        MagicMock(),
    )

    assert result.error_count_downloads == 1
    assert 'promotion failed' in result.failed_downloads['DFP_2023']
    assert not staging_path.exists()
    assert not (output_dir / 'DFP_2023.zip').exists()


@pytest.mark.asyncio
async def test_worker_keeps_loop_live_and_drains_on_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    staging_path = output_dir / 'download.zip.part'
    with zipfile.ZipFile(staging_path, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('payload.txt', 'payload')
        archive.writestr('data.csv', 'id;value\n1;10\n')

    extraction_started = Event()
    release_extraction = Event()
    extraction_finished = Event()
    parquet_path = output_dir / 'data.parquet'

    class BarrierExtractor:
        def extract(self, source_path: str, destination_path: str) -> None:
            extraction_started.set()
            if not release_extraction.wait(timeout=5):
                raise TimeoutError('test barrier was not released')
            ParquetExtractorAdapterCVM().extract(source_path, destination_path)
            extraction_finished.set()

    adapter = AsyncDownloadAdapterCVM(
        file_extractor_repository=BarrierExtractor(),
        automatic_extractor=True,
    )

    async def staged_download(_url, _filepath, _doc_name, _year):
        return True, str(staging_path)

    monkeypatch.setattr(adapter, '_download_with_retry', staged_download)
    result = DownloadResultCVM()
    task = asyncio.create_task(
        adapter._download_and_extract(
            'https://example.com/DFP_2023.zip',
            str(output_dir),
            'DFP',
            '2023',
            result,
            MagicMock(),
            automatic_extractor=True,
        )
    )
    loop_ticks = 0

    async def advance_while_extracting() -> None:
        nonlocal loop_ticks
        while not extraction_started.is_set():
            await asyncio.sleep(0.001)
        for _ in range(3):
            loop_ticks += 1
            await asyncio.sleep(0)

    progress_task = asyncio.create_task(advance_while_extracting())
    try:
        await asyncio.wait_for(progress_task, timeout=3)
        assert loop_ticks == 3
        assert not task.done()

        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release_extraction.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert extraction_finished.is_set()
    assert not staging_path.exists()
    assert not list(output_dir.glob('*.part'))
    assert pq.read_table(parquet_path).to_pylist() == [
        {'id': '1', 'value': '10'}
    ]
    modified_at = parquet_path.stat().st_mtime_ns
    await asyncio.sleep(0.05)
    assert parquet_path.stat().st_mtime_ns == modified_at
