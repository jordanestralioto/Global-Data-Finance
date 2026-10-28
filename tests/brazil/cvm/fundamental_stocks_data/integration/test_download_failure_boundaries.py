"""CVM preflight and publication failures with observable filesystem state."""

from __future__ import annotations

import asyncio
import errno
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_finalization,
    download_paths,
    download_validation,
    parquet_validation,
    transaction,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    AvailableYearsCVM,
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    AsyncDownloadAdapterCVM,
)
from globaldatafinance.core.archive_safety import ArchiveSafetyLimits
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    ExtractionError,
    SecurityError,
)

pytestmark = pytest.mark.integration


def test_non_boolean_extraction_fails_before_directory_creation(
    tmp_path: Path,
) -> None:
    """Invalid extraction configuration cannot create output paths."""
    path = tmp_path / 'output'
    invalid_flag: Any = 1
    with pytest.raises(TypeError, match='must be a boolean'):
        FundamentalStocksDataCVM().download(
            str(path), automatic_extractor=invalid_flag
        )
    assert not path.exists()


def test_year_summary_exposes_the_complete_ipe_history() -> None:
    """IPE history is discoverable with the established namedtuple fields."""
    years = FundamentalStocksDataCVM().get_available_years()
    assert years.ipe_min_year == 2003
    assert AvailableYearsCVM().get_minimal_ipe_year() == 2003
    assert len(years) == 4
    assert years._asdict()['general_min_year'] == 2010


def test_download_target_cannot_follow_an_existing_symlink_outside_destination(
    tmp_path: Path,
) -> None:
    """A portable basename cannot authorize a symlink target elsewhere."""
    destination = tmp_path / 'destination'
    destination.mkdir()
    outside = tmp_path / 'outside.zip'
    outside.write_bytes(b'original')
    (destination / 'source.zip').symlink_to(outside)
    with pytest.raises(SecurityError, match='escapes its destination'):
        download_paths.build_download_target_path(
            'https://example.test/source.zip', str(destination)
        )
    assert outside.read_bytes() == b'original'


def test_malformed_url_preserves_its_parse_failure_as_a_cause(
    tmp_path: Path,
) -> None:
    """Malformed endpoint syntax fails before creating or opening a target."""
    with pytest.raises(SecurityError, match='invalid path') as captured:
        download_paths.build_download_target_path(
            'https://[invalid/source.zip', str(tmp_path)
        )
    assert isinstance(captured.value.__cause__, ValueError)
    assert list(tmp_path.iterdir()) == []


def test_unreadable_source_stat_is_reported_as_failed_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem inspection failure cannot be accepted as a valid ZIP."""
    path = tmp_path / 'source.zip'
    path.write_bytes(b'original')
    original_stat = Path.stat

    def fail_source_stat(candidate, *args, **kwargs):
        if candidate == path:
            raise OSError(errno.EIO, 'source stat unavailable')
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', fail_source_stat)
    assert download_validation.validate_downloaded_file(str(path)) is False
    assert path.read_bytes() == b'original'


@pytest.mark.parametrize('kind', ['null', 'count'])
def test_parquet_data_cannot_hide_nulls_or_an_incorrect_row_count(
    tmp_path: Path, kind: str
) -> None:
    """Complete page reads enforce exact text and the source count."""
    path = tmp_path / 'output.parquet'
    pq.write_table(
        pa.table(
            {
                'value': pa.array(
                    [None] if kind == 'null' else ['1'], type=pa.string()
                )
            }
        ),
        path,
    )
    with (
        pq.ParquetFile(path) as parquet,
        pytest.raises(
            ValueError,
            match='contains nulls' if kind == 'null' else 'row count',
        ),
    ):
        parquet_validation.validate_parquet_data(
            parquet,
            2 if kind == 'count' else 1,
            expected_content_sha256='0' * 64 if kind == 'null' else None,
        )


def test_readable_parquet_from_another_source_cannot_confirm_extraction(
    tmp_path: Path,
) -> None:
    """A readable stale output cannot certify a newly downloaded ZIP."""
    from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
        download_extraction,
    )
    from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
        ParquetExtractorAdapterCVM,
    )

    path = tmp_path / 'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', b'value\noriginal\n')
    ParquetExtractorAdapterCVM().extract(str(path), str(tmp_path))
    previous = (tmp_path / 'data.parquet').read_bytes()
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', b'value\nreplacement\n')
    new_bytes = path.read_bytes()

    class StaleExtractor:
        def extract(self, _source, _destination):
            pass

    result = download_extraction.extract_downloaded_file(
        StaleExtractor(), str(path), str(tmp_path), 'DFP', '2024'
    )
    assert result is not None and 'Parquet validation failed' in result
    assert (tmp_path / 'data.parquet').read_bytes() == previous
    assert path.read_bytes() == new_bytes


def test_missing_source_preserves_outputs_and_its_filesystem_cause(
    tmp_path: Path,
) -> None:
    """An absent source cannot be misreported as a successful empty batch."""
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    limits = ArchiveSafetyLimits(
        max_archive_bytes=1024,
        max_members=3,
        max_member_uncompressed_bytes=1024,
        max_total_uncompressed_bytes=2048,
        max_compression_ratio=100,
    )
    with pytest.raises(ExtractionError) as captured:
        ParquetExtractorAdapterCVM(archive_limits=limits).extract(
            str(tmp_path / 'missing.zip'), str(tmp_path)
        )
    assert isinstance(captured.value.__cause__, FileNotFoundError)
    assert previous.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.cvm-write-lock').exists()


def test_missing_extractor_fails_before_promoting_the_source(
    tmp_path: Path,
) -> None:
    """Invalid finalizer dependencies cannot replace an existing archive."""
    stage = tmp_path / 'source.part'
    stage.write_bytes(b'new source')
    final = tmp_path / 'source.zip'
    final.write_bytes(b'previous source')
    with pytest.raises(RuntimeError, match='requires a CVM Parquet extractor'):
        download_finalization.finalize_downloaded_file(
            stage,
            final,
            str(tmp_path),
            'DFP',
            '2024',
            automatic_extractor=True,
            file_extractor_repository=None,
            validate_file=download_validation.validate_downloaded_file,
            cleanup_file=lambda path: Path(path).unlink(missing_ok=True),
        )
    assert final.read_bytes() == b'previous source'
    assert stage.read_bytes() == b'new source'


@pytest.mark.asyncio
async def test_adapter_rejects_non_boolean_extraction_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct async adapter calls cannot turn truthy values into extraction."""
    adapter = AsyncDownloadAdapterCVM(None)
    stream = AsyncMock()
    monkeypatch.setattr(adapter, '_stream_download', stream)
    invalid_flag: Any = 'yes'
    with pytest.raises(TypeError, match='must be a boolean'):
        await adapter.async_download_docs(
            [
                (
                    'https://example.test/source.zip',
                    'DFP',
                    '2024',
                    str(tmp_path),
                )
            ],
            automatic_extractor=invalid_flag,
        )
    stream.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_waits_for_all_scheduled_downloads_to_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling a campaign cannot leave downloads running after return."""
    adapter = AsyncDownloadAdapterCVM(None, max_concurrent=2)
    active = 0
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def pause_download(*_args, **_kwargs):
        nonlocal active
        active += 1
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1
            stopped.set()

    monkeypatch.setattr(adapter, '_download_and_extract', pause_download)
    tasks = [
        ('https://example.test/source.zip', 'DFP', '2024', str(tmp_path))
    ] * 3
    campaign = asyncio.create_task(
        adapter._run_downloads(tasks, DownloadResultCVM())
    )
    await started.wait()
    campaign.cancel()
    with pytest.raises(asyncio.CancelledError):
        await campaign
    assert stopped.is_set()
    assert active == 0


@pytest.mark.parametrize('failure_type', ['cleanup', 'crc'])
def test_transaction_reports_dependency_failures_without_claiming_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_type: str
) -> None:
    """A failed rollback or changed archive retains actionable causes."""
    path = tmp_path / 'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', b'a;b\n1;2;3\n')
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    failure = OSError(errno.EIO, 'cleanup failed')

    if failure_type == 'cleanup':

        def fail_abort(_self):
            raise failure

        from globaldatafinance.macro_infra.transactional_publication import (
            TransactionalPublication,
        )

        monkeypatch.setattr(TransactionalPublication, 'abort', fail_abort)
        message = 'transaction cleanup also failed'
    else:

        def fail_crc(*_args, **_kwargs):
            raise zipfile.BadZipFile('source changed during verification')

        monkeypatch.setattr(
            transaction, 'validate_zip_crc_with_limits', fail_crc
        )
        message = 'source changed'
    with (
        zipfile.ZipFile(path) as archive,
        pytest.raises(
            ExtractionError
            if failure_type == 'cleanup'
            else CorruptedZipError,
            match=message,
        ),
    ):
        transaction.CvmFailureAtomicBatchCommit(
            str(path), str(tmp_path)
        ).execute(archive)
    assert previous.read_bytes() == b'previous output'
    assert path.exists()
