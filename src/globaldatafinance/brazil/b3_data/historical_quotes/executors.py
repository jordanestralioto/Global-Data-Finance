"""Create bounded B3 executors with caller-owned process initialization."""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
from collections.abc import Callable
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from pathlib import Path
from threading import Event
from typing import Any

from ....core import get_logger
from .processing import ProcessingModeEnumB3

logger = get_logger(__name__)


def _spawn_incompatibility_reason() -> str | None:
    """Inspect caller metadata without importing or executing caller code."""
    if mp.current_process().daemon:
        return 'the calling process is a daemon'
    main = sys.modules.get('__main__')
    spec = getattr(main, '__spec__', None)
    name = getattr(spec, 'name', None)
    if (
        isinstance(name, str)
        and name not in {'', '__main__'}
        and getattr(spec, 'loader', None) is not None
    ):
        return None
    filename = getattr(main, '__file__', None)
    if filename and not str(filename).startswith('<'):
        try:
            path = Path(filename)
            if path.is_file() and os.access(path, os.R_OK):
                return None
        except OSError:
            pass
    return 'the main module has no importable spec or readable script file'


def can_use_b3_processes(
    source_count: int,
    worker_limit: int,
    *,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
) -> bool:
    """Apply the same resource and spawn eligibility policy to both phases."""
    if (
        executor_backend != 'process'
        or processing_mode is not ProcessingModeEnumB3.FAST
        or source_count < 2
        or worker_limit < 2
    ):
        return False
    if reason := _spawn_incompatibility_reason():
        logger.info('B3 process execution unavailable: %s', reason)
        return False
    return True


def create_b3_executor(
    source_count: int,
    worker_limit: int,
    *,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
    initializer: Callable[[Any], None],
) -> tuple[Executor, Any, bool]:
    """Share spawn selection while keeping phase-specific worker ownership."""
    use_processes = can_use_b3_processes(
        source_count,
        worker_limit,
        processing_mode=processing_mode,
        executor_backend=executor_backend,
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
    thread_limit = (
        1
        if processing_mode is ProcessingModeEnumB3.SLOW
        else max(1, min(source_count, worker_limit))
    )
    return ThreadPoolExecutor(max_workers=thread_limit), Event(), False
