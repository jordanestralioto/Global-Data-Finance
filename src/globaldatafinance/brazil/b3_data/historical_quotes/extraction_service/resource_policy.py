"""Admission control for bounded B3 source workers."""

from __future__ import annotations

import asyncio
import gc
import importlib
import os
import time
from collections.abc import Callable
from typing import Protocol, cast

from .....core import (
    ResourceLimits,
    ResourceMonitor,
    ResourceState,
    get_logger,
)
from ..processing import ProcessingModeEnumB3

logger = get_logger(__name__)

_MEBIBYTE = 1024**2
_MEMORY_PER_FAST_WORKER_MIB = 256


class _VirtualMemory(Protocol):
    """Minimum psutil memory snapshot contract used by this policy."""

    available: int


class _PsutilModule(Protocol):
    """Lazy psutil surface required for B3 worker admission."""

    def virtual_memory(self) -> _VirtualMemory:
        """Return one available-memory snapshot."""


class ResourcePolicyB3:
    """Own B3 admission control without collecting garbage in hot parsing."""

    def __init__(
        self,
        processing_mode: ProcessingModeEnumB3,
        resource_monitor: ResourceMonitor | None = None,
        available_memory_mib: Callable[[], int] | None = None,
    ) -> None:
        """Store the selected mode and a monitor with warning GC disabled."""
        self.processing_mode = processing_mode
        self.resource_monitor = (
            resource_monitor
            or ResourceMonitor.create_isolated(
                ResourceLimits(
                    auto_gc_on_warning=False,
                    cpu_warning_threshold=101.0,
                    cpu_critical_threshold=101.0,
                )
            )
        )
        self._available_memory_mib = (
            available_memory_mib or self._read_available_memory_mib
        )

    @staticmethod
    def _read_available_memory_mib() -> int:
        """Return available RAM in MiB without retaining a large snapshot."""
        try:
            psutil_module = cast(
                _PsutilModule, importlib.import_module('psutil')
            )
            return int(psutil_module.virtual_memory().available // _MEBIBYTE)
        except (ImportError, OSError):
            return _MEMORY_PER_FAST_WORKER_MIB

    def worker_limit(self, file_count: int) -> int:
        """Calculate the exact fast/slow worker limit for this request."""
        if file_count <= 0:
            return 1
        if self.processing_mode is ProcessingModeEnumB3.SLOW:
            return 1
        memory_bound = (
            self._available_memory_mib() * 0.5 // _MEMORY_PER_FAST_WORKER_MIB
        )
        return max(
            1,
            min(
                4,
                file_count,
                os.cpu_count() or 1,
                int(memory_bound),
            ),
        )

    async def await_admission(self, timeout_seconds: int = 30) -> bool:
        """Wait while critical and fail safely when resources are exhausted."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self.resource_monitor.check_resources()
            if state in (ResourceState.HEALTHY, ResourceState.WARNING):
                if state is ResourceState.WARNING:
                    logger.warning(
                        'B3 extraction continues under memory warning'
                    )
                return True
            if state is ResourceState.EXHAUSTED:
                return False
            if time.monotonic() >= deadline:
                return False
            logger.warning(
                'B3 extraction pauses admission under critical memory'
            )
            await asyncio.sleep(0.25)

    def collect_after_critical_flush(self) -> None:
        """Collect once only after a completed worker flush under pressure."""
        if self.resource_monitor.check_resources() is ResourceState.CRITICAL:
            gc.collect()
