"""Create bounded B3 executors with caller-owned process initialization."""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from threading import Event
from typing import Any

from .processing import ProcessingModeEnumB3


def create_b3_executor(
    source_count: int,
    worker_limit: int,
    *,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
    initializer: Callable[[Any], None],
) -> tuple[Executor, Any, bool]:
    """Share spawn selection while keeping phase-specific worker ownership."""
    use_processes = (
        executor_backend == 'process'
        and processing_mode is ProcessingModeEnumB3.FAST
        and source_count >= 2
        and worker_limit >= 2
    )
    if use_processes:
        context = mp.get_context('spawn')
        cancel_event = context.Event()
        return (
            ProcessPoolExecutor(
                max_workers=worker_limit,
                mp_context=context,
                initializer=initializer,
                initargs=(cancel_event,),
            ),
            cancel_event,
            True,
        )
    return ThreadPoolExecutor(max_workers=worker_limit), Event(), False
