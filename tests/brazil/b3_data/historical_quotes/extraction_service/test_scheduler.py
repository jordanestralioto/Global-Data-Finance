"""Unit tests for asynchronous B3 worker shutdown."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)

pytestmark = pytest.mark.unit


class _BlockingExecutor:
    """Executor double that makes an event-loop block observable."""

    def __init__(self) -> None:
        """Initialize shutdown observations."""
        self.calls: list[tuple[bool, bool]] = []

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        """Block long enough to distinguish a thread from the event loop."""
        self.calls.append((wait, cancel_futures))
        time.sleep(0.25)


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
    loop = asyncio.get_running_loop()
    probe: asyncio.Future[float] = loop.create_future()
    started = time.perf_counter()
    loop.call_later(
        0.02,
        lambda: probe.set_result(time.perf_counter()),
    )

    shutdown = asyncio.create_task(
        extraction_service.scheduler.ExtractionSchedulerB3._shutdown_executor(
            executor,
            cancel_event,
            cancel_futures=True,
        )
    )
    observed = await asyncio.wait_for(probe, timeout=1.0)
    await shutdown

    assert observed - started < 0.15
    assert cancel_event.signaled.is_set()
    assert executor.calls == [(True, True)]
