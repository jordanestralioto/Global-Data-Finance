"""Joined B3 phase execution propagates context, errors, and cancellation."""

import asyncio
import threading
from contextvars import ContextVar

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    async_execution,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_phase_preserves_context_and_returns_its_value() -> None:
    """Source execution retains caller tracing and positional arguments."""
    caller = ContextVar('test_b3_caller', default='unset')
    token = caller.set('caller')
    loop_thread = threading.get_ident()

    def operation(value, *, suffix):
        assert threading.get_ident() != loop_thread
        return caller.get(), value + suffix

    try:
        result = await async_execution.run_blocking_phase(
            operation, 'a', suffix='b'
        )
    finally:
        caller.reset(token)

    assert result == ('caller', 'ab')


async def test_phase_propagates_original_error() -> None:
    """A failed blocking phase preserves its diagnostic cause."""
    error = OSError('source read failed')

    def fail():
        raise error

    with pytest.raises(OSError, match='source read failed') as caught:
        await async_execution.run_blocking_phase(fail)

    assert caught.value is error


async def test_repeated_cancellation_joins_worker() -> None:
    """Repeated cancel requests cannot detach in-flight phase work."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocked_read():
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(timeout=5)
            async_execution.check_phase_cancellation()
        finally:
            finished.set()

    task = asyncio.create_task(
        async_execution.run_blocking_phase(blocked_read)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not finished.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert finished.is_set()
    assert not any(
        thread.name.startswith('gdf-b3-phase')
        for thread in threading.enumerate()
    )


async def test_atomic_phase_returns_outcome_after_cancel_requests() -> None:
    """The atomic decision finishes and consumes only new cancellation."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()

    def commit():
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(timeout=5)
            async_execution.check_phase_cancellation()
            return 'committed'
        finally:
            finished.set()

    task = asyncio.create_task(async_execution.run_atomic_phase(commit))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        outcome = await task

    assert outcome == 'committed'
    assert finished.is_set()
    assert not task.cancelled()
    assert task.cancelling() == 0


async def test_publication_verification_is_cancellable_before_decision() -> (
    None
):
    """A cancelled final source check cannot advance to publication."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    checked = threading.Event()
    published = threading.Event()

    def verify():
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        checked.set()

    def publish():
        published.set()
        return 'committed'

    task = asyncio.create_task(
        async_execution.run_publication_phase(verify, publish)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert checked.is_set()
    assert not published.is_set()
    assert not any(
        thread.name.startswith('gdf-b3-phase')
        for thread in threading.enumerate()
    )


async def test_publication_late_cancellation_returns_actual_commit() -> None:
    """After verification, repeated cancellation joins the real decision."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    phase_threads = []

    def verify():
        phase_threads.append(threading.get_ident())

    def publish():
        phase_threads.append(threading.get_ident())
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return 'committed'

    task = asyncio.create_task(
        async_execution.run_publication_phase(verify, publish)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        outcome = await task

    assert outcome == 'committed'
    assert len(phase_threads) == 2
    assert phase_threads[0] == phase_threads[1] != threading.get_ident()
    assert not task.cancelled()
    assert task.cancelling() == 0


async def test_publication_verification_failure_preserves_cause() -> None:
    """A verification error is returned without invoking commit."""
    error = OSError('source removed before publication')
    published = []

    def verify():
        raise error

    def publish():
        published.append(True)

    with pytest.raises(OSError, match='source removed') as caught:
        await async_execution.run_publication_phase(verify, publish)

    assert caught.value is error
    assert published == []
