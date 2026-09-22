"""Integration tests for B3 multiprocessing worker and process backend."""

import asyncio
import multiprocessing as mp
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import psutil
import pyarrow.parquet as pq
import pytest

from globaldatafinance.application.b3_docs import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    ExtractionServiceB3,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _service(
    mode: ProcessingModeEnumB3,
    backend: str = 'process',
) -> ExtractionServiceB3:
    """Build an extraction service configured with chosen execution backend."""
    return ExtractionServiceB3(
        zip_reader=ZipFileReaderB3(),
        parser=CotahistParserB3(),
        processing_mode=mode,
        executor_backend=backend,
    )


def _non_tracker_child_processes() -> list[psutil.Process]:
    """Return child workers while tolerating a process exiting mid-read."""
    workers: list[psutil.Process] = []
    for child in psutil.Process().children(recursive=True):
        try:
            if 'resource_tracker' not in ' '.join(child.cmdline()):
                workers.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return workers


def test_process_source_worker_spawns_and_extracts_to_parquet(
    tmp_path: Path,
) -> None:
    """Spawned child process extracts source and writes temporary Parquet."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024, ticker='PETR4'),
            build_cotahist_record(year=2024, ticker='VALE3'),
        ],
    )
    staging_dir = tmp_path / 'staging'
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_output = staging_dir / '00000.parquet'

    ctx = mp.get_context('spawn')
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(
            extraction_service.process_worker.process_source_worker,
            str(source),
            {'010'},
            str(temp_output),
        )
        result = future.result(timeout=10)

    assert result.temp_path == temp_output
    assert result.written_records == 2
    assert temp_output.exists()
    assert pq.ParquetFile(temp_output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


def test_process_worker_cooperative_cancellation_cleans_up(
    tmp_path: Path,
) -> None:
    """Cancelled worker raises ProcessingCancelled and leaves no files."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    staging_dir = tmp_path / 'staging'
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_output = staging_dir / 'cancelled.parquet'

    ctx = mp.get_context('spawn')
    cancel_event = ctx.Event()
    cancel_event.set()

    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=ctx,
        initializer=extraction_service.process_worker.init_worker,
        initargs=(cancel_event,),
    ) as executor:
        future = executor.submit(
            extraction_service.process_worker.process_source_worker,
            str(source),
            {'010'},
            str(temp_output),
        )
        with pytest.raises(
            extraction_service.zip_processor.ProcessingCancelled
        ):
            future.result(timeout=10)

    assert not temp_output.exists()
    assert not _non_tracker_child_processes()


def test_processing_cancelled_bypasses_retry() -> None:
    """ProcessingCancelled must never trigger retry loop iterations."""
    attempts = 0

    def faulty_operation() -> None:
        nonlocal attempts
        attempts += 1
        raise extraction_service.zip_processor.ProcessingCancelled(
            'mock_source', 'cancelled'
        )

    with pytest.raises(extraction_service.zip_processor.ProcessingCancelled):
        extraction_service.retry.retry_unpublished_io(faulty_operation)

    assert attempts == 1


@pytest.mark.asyncio
async def test_process_backend_failure_isolation_rolls_back_cleanly(
    tmp_path: Path,
) -> None:
    """A corrupted source in process pool aborts transaction and staging."""
    valid = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    malformed = write_cotahist_txt(
        tmp_path,
        year=2025,
        records=[build_cotahist_record(year=2025)[:244]],
    )
    output = tmp_path / 'failed_quotes.parquet'

    service = _service(ProcessingModeEnumB3.FAST, backend='process')
    result = await service.extract_from_zip_files(
        {str(valid), str(malformed)}, {'010'}, output
    )

    assert result['success_count'] == 0
    assert result['error_count'] >= 1
    assert result['total_records'] == 0
    assert not output.exists()
    assert list(tmp_path.glob('.globaldatafinance-transaction-*')) == []
    assert 'COTAHIST_A2025.TXT' in result['errors']
    err_msg = result['errors']['COTAHIST_A2025.TXT']
    assert 'BrokenProcessPool' not in err_msg
    assert 'ExtractionError' in err_msg
    assert 'Expected exactly 245 characters' in err_msg


def test_processing_cancelled_pickle_roundtrip() -> None:
    """ProcessingCancelled round-trips through pickle without losing state."""
    err = extraction_service.zip_processor.ProcessingCancelled(
        '/path/to/source.zip', 'user cancel'
    )
    attr = 'loads'
    loaded = getattr(pickle, attr)(pickle.dumps(err))
    assert type(loaded) is extraction_service.zip_processor.ProcessingCancelled
    assert str(loaded) == str(err)
    assert loaded.path == err.path
    assert loaded.message == err.message


@pytest.mark.asyncio
async def test_process_pool_spawn_error_propagation_preserves_b3_cause(
    tmp_path: Path,
) -> None:
    """Spawn pool preserves original ExtractionError without broken pool."""
    empty = write_cotahist_txt(tmp_path, year=2024, records=[])
    valid = write_cotahist_txt(
        tmp_path,
        year=2025,
        records=[build_cotahist_record(year=2025, ticker='VALE3')],
    )
    output = tmp_path / 'empty_error_test.parquet'
    service = _service(ProcessingModeEnumB3.FAST, backend='process')
    result = await service.extract_from_zip_files(
        {str(empty), str(valid)}, {'010'}, output
    )

    assert result['success_count'] == 0
    assert result['error_count'] >= 1
    assert 'COTAHIST_A2024.TXT' in result['errors']
    err_text = result['errors']['COTAHIST_A2024.TXT']
    assert 'BrokenProcessPool' not in err_text
    assert 'ExtractionError' in err_text
    assert 'no type-01 quote data record' in err_text


@pytest.mark.asyncio
async def test_process_backend_logical_parity_with_thread_backend(
    tmp_path: Path,
) -> None:
    """Process backend produces identical Parquet rows, types, and schema."""
    first = write_cotahist_txt(
        tmp_path,
        year=2023,
        records=[
            build_cotahist_record(year=2023, ticker='BBDC4'),
            build_cotahist_record(year=2023, ticker='PETR4'),
        ],
    )
    second = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024, ticker='ITUB4'),
            build_cotahist_record(year=2024, ticker='VALE3'),
        ],
    )
    out_thread = tmp_path / 'quotes_thread.parquet'
    out_process = tmp_path / 'quotes_process.parquet'

    sources = {str(first), str(second)}
    markets = {'010'}

    service_thread = _service(ProcessingModeEnumB3.FAST, backend='thread')
    result_thread = await service_thread.extract_from_zip_files(
        sources, markets, out_thread
    )

    service_process = _service(ProcessingModeEnumB3.FAST, backend='process')
    result_process = await service_process.extract_from_zip_files(
        sources, markets, out_process
    )

    assert result_thread['success_count'] == 2
    assert result_process['success_count'] == 2
    assert result_thread['total_records'] == 4
    assert result_process['total_records'] == 4
    assert result_thread['error_count'] == 0
    assert result_process['error_count'] == 0

    table_thread = pq.read_table(out_thread)
    table_process = pq.read_table(out_process)

    assert table_process.schema.equals(table_thread.schema)
    assert table_process.num_rows == table_thread.num_rows
    assert table_process.column_names == table_thread.column_names
    assert table_process.to_pydict() == table_thread.to_pydict()

    phase_timings = service_process.last_phase_timings
    assert phase_timings['source_wall_seconds'] is not None
    assert phase_timings['merge_wall_seconds'] is not None
    assert phase_timings['merge_status'] == 'completed'
    assert phase_timings['validation_wall_seconds'] is not None


@pytest.mark.asyncio
async def test_single_source_bypasses_process_backend_and_merge(
    tmp_path: Path,
) -> None:
    """Single source uses thread backend even when process backend opted-in."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    output = tmp_path / 'single.parquet'

    service = _service(ProcessingModeEnumB3.FAST, backend='process')
    result = await service.extract_from_zip_files(
        {str(source)}, {'010'}, output
    )

    assert result['success_count'] == 1
    assert result['total_records'] == 1
    assert service.last_phase_timings['merge_status'] == 'bypassed'
    assert service.last_phase_timings['merge_wall_seconds'] is None


@pytest.mark.asyncio
async def test_single_filtered_source_reports_completed_empty_merge(
    tmp_path: Path,
) -> None:
    """Empty output is a real merge, not a single-source direct publication."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024, ticker='PETR4', market='070')
        ],
    )
    output = tmp_path / 'single_filtered.parquet'
    service = _service(ProcessingModeEnumB3.FAST, backend='thread')

    result = await service.extract_from_zip_files(
        {str(source)}, {'010'}, output
    )

    assert result['success_count'] == 1
    assert result['total_records'] == 0
    assert output.is_file()
    assert service.last_phase_timings['merge_status'] == 'completed'
    assert service.last_phase_timings['merge_wall_seconds'] is not None


def test_historical_quotes_b3_facade_extract_with_process_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HistoricalQuotesB3 facade completes extraction with process backend."""
    write_cotahist_txt(
        tmp_path,
        year=2023,
        records=[build_cotahist_record(year=2023, ticker='PETR4')],
    )
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='VALE3')],
    )
    out_name = 'facade_process.parquet'

    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'process')
    client = HistoricalQuotesB3()
    result = client.extract(
        path_of_docs=str(tmp_path),
        assets_list=['ações'],
        initial_year=2023,
        last_year=2024,
        destination_path=str(tmp_path),
        output_filename=out_name,
        processing_mode='fast',
    )

    assert result['success'] is True
    output_path = tmp_path / out_name
    assert output_path.exists()
    assert pq.ParquetFile(output_path).metadata.num_rows == 2
    assert client._last_phase_timings['merge_status'] == 'completed'


def test_process_worker_cancellation_during_dense_filtered_sweep(
    tmp_path: Path,
) -> None:
    """Worker aborts promptly on cancellation during dense filtered scan."""
    records = [
        build_cotahist_record(year=2024, ticker='PETR4', market='070')
        for _ in range(2_500)
    ]
    source = write_cotahist_txt(tmp_path, year=2024, records=records)
    temp_output = tmp_path / 'filtered.parquet'

    ctx = mp.get_context('spawn')
    cancel_event = ctx.Event()
    cancel_event.set()

    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=ctx,
        initializer=extraction_service.process_worker.init_worker,
        initargs=(cancel_event,),
    ) as executor:
        future = executor.submit(
            extraction_service.process_worker.process_source_worker,
            str(source),
            {'010'},
            str(temp_output),
        )
        with pytest.raises(
            extraction_service.zip_processor.ProcessingCancelled
        ):
            future.result(timeout=10)

    assert not temp_output.exists()


def test_historical_quotes_b3_invalid_backend_fails_fast_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid backend raises ValueError fast with zero filesystem effects."""
    before_entries = set(tmp_path.iterdir())
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'invalid')
    with pytest.raises(
        ValueError,
        match="Invalid executor_backend: 'invalid'",
    ):
        HistoricalQuotesB3()
    assert set(tmp_path.iterdir()) == before_entries


def test_historical_quotes_b3_last_phase_timings_reset_on_empty_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase timings are cleared and isolated between successful and empty."""
    write_cotahist_txt(
        tmp_path,
        year=2023,
        records=[build_cotahist_record(year=2023, ticker='PETR4')],
    )
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='VALE3')],
    )
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'process')
    client = HistoricalQuotesB3()
    res1 = client.extract(
        path_of_docs=str(tmp_path),
        assets_list=['ações'],
        initial_year=2023,
        last_year=2024,
        output_filename='run1.parquet',
        processing_mode='fast',
    )
    assert res1['success'] is True
    assert client._last_phase_timings['merge_status'] == 'completed'
    assert client._last_phase_timings['source_wall_seconds'] > 0.0

    res2 = client.extract(
        path_of_docs=str(tmp_path),
        assets_list=['ações'],
        initial_year=2010,
        last_year=2010,
        output_filename='run2.parquet',
        processing_mode='fast',
    )
    assert res2['success'] is True
    assert res2['total_files'] == 0
    assert client._last_phase_timings['merge_status'] == 'bypassed'
    assert client._last_phase_timings['source_wall_seconds'] == 0.0
    assert client._last_phase_timings['validation_wall_seconds'] == 0.0


@pytest.mark.asyncio
async def test_active_process_pool_cancellation_cleans_up_bounded(
    tmp_path: Path,
) -> None:
    """Multi-process extraction cancels cooperatively with bounded cleanup."""
    first = write_cotahist_txt(
        tmp_path,
        year=2023,
        records=[
            build_cotahist_record(year=2023, ticker='PETR4', market='070')
            for _ in range(15_000)
        ],
    )
    second = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024, ticker='VALE3', market='070')
            for _ in range(15_000)
        ],
    )
    output = tmp_path / 'cancelled_active.parquet'
    output.write_text('previous content', encoding='utf-8')

    service = _service(ProcessingModeEnumB3.FAST, backend='process')

    task = asyncio.create_task(
        service.extract_from_zip_files(
            {str(first), str(second)},
            {'010'},
            output,
        )
    )
    deadline = time.monotonic() + 5.0
    workers_observed: list[psutil.Process] = []
    while time.monotonic() < deadline:
        workers_observed = _non_tracker_child_processes()
        if len(workers_observed) >= 2:
            break
        await asyncio.sleep(0.01)

    assert len(workers_observed) >= 2, (
        f'Expected at least 2 active worker processes, found '
        f'{len(workers_observed)}'
    )
    observed_worker_pids = {worker.pid for worker in workers_observed}
    task.cancel()

    start_cancel = time.perf_counter()
    with pytest.raises(asyncio.CancelledError):
        await task
    cancel_duration = time.perf_counter() - start_cancel

    assert cancel_duration < 5.0
    assert output.exists()
    assert output.read_text(encoding='utf-8') == 'previous content'

    staging_dirs = list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert staging_dirs == []

    assert not _non_tracker_child_processes()
    assert all(not psutil.pid_exists(pid) for pid in observed_worker_pids)
