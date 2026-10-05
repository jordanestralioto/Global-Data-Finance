"""Unit tests for asynchronous B3 worker shutdown."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    ExtractionServiceB3,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.unit


class _BlockingExecutor:
    """Executor double observing event-loop blocks via a barrier."""

    def __init__(self) -> None:
        """Initialize shutdown observations and synchronization barriers."""
        self.calls: list[tuple[bool, bool]] = []
        self.shutdown_entered = threading.Event()
        self.shutdown_release = threading.Event()
        self.shutdown_thread_id: int | None = None

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        """Block until released by the loop to prove non-blocking run."""
        self.shutdown_thread_id = threading.get_ident()
        self.calls.append((wait, cancel_futures))
        self.shutdown_entered.set()
        self.shutdown_release.wait(timeout=5.0)


class _CancellationEvent:
    """Minimal cancellation event used by the scheduler shutdown seam."""

    def __init__(self) -> None:
        """Initialize an observable signal state."""
        self.signaled = threading.Event()

    def set(self) -> None:
        """Record cancellation requested by the parent task."""
        self.signaled.set()


@pytest.mark.asyncio
async def test_process_shutdown_does_not_block_the_event_loop() -> None:
    """Cooperative process cleanup leaves the event loop responsive."""
    executor = _BlockingExecutor()
    cancel_event = _CancellationEvent()
    loop_thread_id = threading.get_ident()

    shutdown = asyncio.create_task(
        extraction_service.scheduler.ExtractionSchedulerB3._shutdown_executor(
            executor,
            cancel_event,
            cancel_futures=True,
        )
    )

    try:
        await asyncio.to_thread(executor.shutdown_entered.wait, 5.0)
        assert executor.shutdown_entered.is_set()
        assert executor.shutdown_thread_id is not None
        assert executor.shutdown_thread_id != loop_thread_id
        assert not shutdown.done()

        loop_responsive = False
        await asyncio.sleep(0.01)
        loop_responsive = True

        assert not shutdown.done()
        assert loop_responsive
    finally:
        executor.shutdown_release.set()

    await shutdown

    assert cancel_event.signaled.is_set()
    assert executor.calls == [(True, True)]


def test_thread_workers_receive_an_isolated_cancellation_event(
    tmp_path: Path,
) -> None:
    """Cancelling one run stops its source without poisoning a later run."""
    service = ExtractionServiceB3(
        ZipFileReaderB3(), CotahistParserB3(), ProcessingModeEnumB3.FAST
    )
    scheduler = extraction_service.scheduler.ExtractionSchedulerB3(
        service.zip_processor,
        service.zip_reader,
        service.resource_policy,
        processing_mode=ProcessingModeEnumB3.FAST,
    )
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    for cancel in (True, False):
        executor, event, processes = scheduler._create_executor(1, 1)
        try:
            assert event is not None
            if cancel:
                event.set()
            future = scheduler._submit_source(
                executor,
                str(source),
                {'010'},
                tmp_path / 'staged.parquet',
                use_processes=processes,
                cancel_event=event,
                source_descriptor=None,
                all_markets=True,
                schema_metadata=None,
            )
            if cancel:
                with pytest.raises(
                    extraction_service.zip_processor.ProcessingCancelled
                ):
                    future.result(timeout=5)
                assert not (tmp_path / 'staged.parquet').exists()
            else:
                assert future.result(timeout=5).written_records == 1
            assert service.zip_processor.cancel_event is None
        finally:
            executor.shutdown(wait=True, cancel_futures=True)


def test_thread_cancellation_removes_a_partially_written_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cooperative stop closes the writer and removes its private output."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()] * 1_003
    )
    descriptor = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        all_markets=True,
        target_tpmerc_codes=set(),
    ).sources[0]
    service = ExtractionServiceB3(
        ZipFileReaderB3(), CotahistParserB3(), ProcessingModeEnumB3.FAST
    )
    service.zip_processor.python_record_limit = 100
    scheduler = extraction_service.scheduler.ExtractionSchedulerB3(
        service.zip_processor,
        service.zip_reader,
        service.resource_policy,
        processing_mode=ProcessingModeEnumB3.FAST,
    )
    executor, event, processes = scheduler._create_executor(1, 1)
    assert event is not None
    output = tmp_path / 'partial.parquet'
    saw_private_output = []
    read_lines = service.zip_reader.iter_raw_lines

    def cancel_after_one_batch(*args, **kwargs):
        for index, raw_line in enumerate(read_lines(*args, **kwargs)):
            if index == 201:
                saw_private_output.append(output.exists())
                event.set()
            yield raw_line

    monkeypatch.setattr(
        service.zip_reader, 'iter_raw_lines', cancel_after_one_batch
    )
    try:
        future = scheduler._submit_source(
            executor,
            str(source),
            set(),
            output,
            use_processes=processes,
            cancel_event=event,
            source_descriptor=descriptor,
            all_markets=True,
            schema_metadata=None,
        )
        with pytest.raises(
            extraction_service.zip_processor.ProcessingCancelled
        ):
            future.result(timeout=5)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    assert saw_private_output == [True]
    assert not output.exists()
    assert service.zip_processor.cancel_event is None


@pytest.mark.asyncio
async def test_repeated_cancel_during_shutdown_keeps_the_loop_responsive():
    """Joining remains asynchronous until workers finish after two cancels."""
    executor = _BlockingExecutor()
    shutdown = asyncio.create_task(
        extraction_service.scheduler.ExtractionSchedulerB3._shutdown_executor(
            executor,
            _CancellationEvent(),
            cancel_futures=True,
        )
    )
    try:
        await asyncio.to_thread(executor.shutdown_entered.wait, 5)
        assert executor.shutdown_entered.is_set()
        shutdown.cancel()
        await asyncio.sleep(0)
        shutdown.cancel()
        await asyncio.sleep(0)
        assert not shutdown.done()
    finally:
        executor.shutdown_release.set()
        with pytest.raises(asyncio.CancelledError):
            await shutdown

    assert executor.calls == [(True, True)]
