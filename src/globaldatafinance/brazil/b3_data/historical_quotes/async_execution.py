"""Run blocking B3 phases with cooperative cancellation and joined work."""

from __future__ import annotations

import asyncio
from _thread import LockType
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import ContextVar, Token, copy_context
from functools import partial
from threading import Event, Lock

from ....core import get_logger

_phase_stop: ContextVar[Event | None] = ContextVar(
    'b3_phase_stop', default=None
)
logger = get_logger(__name__)


def set_phase_cancellation(stop: Event | None) -> Token[Event | None]:
    """Bind cooperative cancellation to the current execution context."""
    return _phase_stop.set(stop)


def reset_phase_cancellation(token: Token[Event | None]) -> None:
    """Restore the cancellation context that preceded the binding."""
    _phase_stop.reset(token)


def check_phase_cancellation() -> None:
    """Stop a blocking phase at a bounded I/O or record-batch boundary."""
    stop = _phase_stop.get()
    if stop is not None and stop.is_set():
        raise asyncio.CancelledError


async def run_blocking_phase[**P, T](
    operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Keep the event loop responsive and join work before returning."""
    return await _run_joined_phase(
        partial(operation, *args, **kwargs), cancellable=True
    )


async def run_atomic_phase[**P, T](
    operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Finish a publication decision without blocking the event loop."""
    return await _run_joined_phase(
        partial(operation, *args, **kwargs), cancellable=False
    )


async def run_publication_phase[T](
    verify: Callable[[], None], publish: Callable[[], T]
) -> T:
    """Verify cancellably and publish in the same joined worker."""
    decision = Event()
    decision_lock = Lock()
    return await _run_joined_phase(
        partial(verify_and_publish, verify, publish, decision, decision_lock),
        cancellable=True,
        publication_started=decision,
        publication_lock=decision_lock,
    )


def verify_and_publish[T](
    verify: Callable[[], None],
    publish: Callable[[], T],
    decision: Event,
    decision_lock: LockType,
) -> T:
    """Verify cancellably and record the atomic publication decision."""
    verify()
    with decision_lock:
        check_phase_cancellation()
        decision.set()
    return publish()


async def _run_joined_phase[T](
    operation: Callable[[], T],
    *,
    cancellable: bool,
    publication_started: Event | None = None,
    publication_lock: LockType | None = None,
) -> T:
    stop = Event()
    context = copy_context()
    task = asyncio.current_task()
    initial_cancellations = 0 if task is None else task.cancelling()
    with ThreadPoolExecutor(
        max_workers=1, thread_name_prefix='gdf-b3-phase'
    ) as executor:
        submitted = executor.submit(context.run, run_phase, stop, operation)
        future = asyncio.wrap_future(submitted)
        try:
            if not cancellable:
                return await _await_atomic_phase(future)
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            with publication_lock or nullcontext():
                stop.set()
            await _drain_cancelled_phase(future)
            if (
                publication_started is not None
                and publication_started.is_set()
            ):
                if task is not None:
                    _consume_cancellations(task, initial_cancellations)
                return future.result()
            raise


async def _await_atomic_phase[T](future: asyncio.Future[T]) -> T:
    task = asyncio.current_task()
    initial_cancellations = 0 if task is None else task.cancelling()
    while True:
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            if future.done() and (
                future.cancelled()
                or isinstance(future.exception(), asyncio.CancelledError)
            ):
                raise
            if task is not None:
                _consume_cancellations(task, initial_cancellations)


def _consume_cancellations(
    task: asyncio.Task, initial_cancellations: int
) -> None:
    while task.cancelling() > initial_cancellations:
        task.uncancel()


def run_phase[T](stop: Event, operation: Callable[[], T]) -> T:
    """Run an operation with scoped cooperative cancellation."""
    token = _phase_stop.set(stop)
    try:
        return operation()
    finally:
        _phase_stop.reset(token)


async def _drain_cancelled_phase[T](future: asyncio.Future[T]) -> None:
    """Handle repeated cancellation without orphaning a reader or writer."""
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            continue
        except Exception:
            logger.exception('B3 blocking phase failed during cancellation')
            return
    if not future.cancelled():
        error = future.exception()
        if isinstance(error, Exception):
            logger.error(
                'B3 blocking phase failed while draining cancellation',
                exc_info=(type(error), error, error.__traceback__),
            )
