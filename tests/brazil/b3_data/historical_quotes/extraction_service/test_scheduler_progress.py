"""Unit tests for B3 progress on worker completion and cancellation."""

import asyncio
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def scheduler_with_executor(monkeypatch: pytest.MonkeyPatch):
    """Keep scheduler logic real while replacing OS resource and worker I/O."""
    resource_policy = Mock()
    resource_policy.worker_limit.return_value = 1
    resource_policy.await_admission = AsyncMock(return_value=True)
    scheduler = extraction_service.scheduler.ExtractionSchedulerB3(
        Mock(),
        Mock(),
        resource_policy,
        processing_mode=ProcessingModeEnumB3.FAST,
    )
    executor = Mock()
    cancellation = Mock()
    monkeypatch.setattr(
        scheduler,
        '_create_executor',
        Mock(return_value=(executor, cancellation, False)),
    )
    return scheduler, executor, cancellation


@pytest.mark.asyncio
@pytest.mark.parametrize('worker_fails', [False, True])
async def test_progress_counts_completed_workers_once(
    scheduler_with_executor,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    worker_fails: bool,
) -> None:
    """Completed attempts advance the count once, including reported errors."""
    scheduler, executor, _cancellation = scheduler_with_executor
    futures: list[Future[extraction_service.types.SourceExtractionResult]] = []
    for _ in range(2):
        future: Future[extraction_service.types.SourceExtractionResult] = (
            Future()
        )
        if worker_fails:
            future.set_exception(OSError('worker write failed'))
        else:
            future.set_result(
                Mock(spec=extraction_service.types.SourceExtractionResult)
            )
        futures.append(future)
    submit = Mock(side_effect=futures)
    monkeypatch.setattr(scheduler, '_submit_source', submit)

    state = await scheduler.run_sources(
        ['first.txt', 'second.txt'], {'010'}, Path('/unused-staging')
    )

    output = capsys.readouterr().out
    assert '0/2 (0%)' in output
    assert output.endswith('\n')
    if worker_fails:
        assert '1/2 (50%)' in output
        assert '(100%)' not in output
        assert state.results == {}
        assert state.errors == {'first.txt': 'OSError: worker write failed'}
        assert submit.call_count == 1
    else:
        assert '2/2 (100%)' in output
        assert set(state.results) == {0, 1}
        assert state.errors == {}
        assert submit.call_count == 2
    executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)


@pytest.mark.asyncio
async def test_cancellation_closes_progress_without_counting_running_work(
    scheduler_with_executor,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cancellation preserves the initial count until an attempt completes."""
    scheduler, executor, cancellation = scheduler_with_executor
    worker_submitted = asyncio.Event()
    pending: Future[extraction_service.types.SourceExtractionResult] = Future()

    def submit_worker(*_args, **_kwargs):
        worker_submitted.set()
        return pending

    monkeypatch.setattr(scheduler, '_submit_source', submit_worker)
    task = asyncio.create_task(
        scheduler.run_sources(['first.txt'], {'010'}, Path('/unused-staging'))
    )
    try:
        await asyncio.wait_for(worker_submitted.wait(), timeout=5)
        assert '0/1 (0%)' in capsys.readouterr().out
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    output = capsys.readouterr().out
    assert '0/1 (0%)' in output
    assert '(100%)' not in output
    assert output.endswith('\n')
    cancellation.set.assert_called_once()
    executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('worker_fails', [False, True])
async def test_worker_completion_wakes_scheduler_without_polling(
    scheduler_with_executor,
    monkeypatch: pytest.MonkeyPatch,
    worker_fails: bool,
) -> None:
    """Both worker outcomes trigger admission/draining without timed sleeps."""
    scheduler, executor, _cancellation = scheduler_with_executor
    pending: Future[extraction_service.types.SourceExtractionResult] = Future()
    result = Mock(spec=extraction_service.types.SourceExtractionResult)

    def submit_worker(*_args, **_kwargs):
        loop = asyncio.get_running_loop()
        if worker_fails:
            loop.call_soon(pending.set_exception, OSError('worker failed'))
        else:
            loop.call_soon(pending.set_result, result)
        return pending

    monkeypatch.setattr(scheduler, '_submit_source', submit_worker)
    sleep = AsyncMock(side_effect=AssertionError('polling is forbidden'))
    monkeypatch.setattr(extraction_service.scheduler.asyncio, 'sleep', sleep)

    state = await scheduler.run_sources(
        ['first.txt'], {'010'}, Path('/unused-staging')
    )

    sleep.assert_not_awaited()
    if worker_fails:
        assert state.results == {}
        assert state.errors == {'first.txt': 'OSError: worker failed'}
    else:
        assert state.results == {0: result}
        assert state.errors == {}
    executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)
