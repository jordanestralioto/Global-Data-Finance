"""Unit tests for asynchronous B3 worker shutdown."""

from __future__ import annotations

import asyncio
import threading

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)

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
