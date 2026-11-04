"""Process memory sampling for isolated benchmark runs."""

from __future__ import annotations

import importlib
import threading
from typing import Any, Protocol, cast


class _MemoryInfo(Protocol):
    """The psutil memory fields used by the benchmark sampler."""

    rss: int


class _Process(Protocol):
    """The psutil process API used by the benchmark sampler."""

    pid: int

    def memory_info(self) -> _MemoryInfo: ...

    def children(self, *, recursive: bool = ...) -> list[_Process]: ...


class _VirtualMemory(Protocol):
    """The psutil virtual-memory field used in benchmark metadata."""

    available: int


class _PsutilModule(Protocol):
    """The narrow runtime psutil contract needed by this script."""

    Error: type[Exception]
    NoSuchProcess: type[Exception]
    AccessDenied: type[Exception]

    def Process(self) -> _Process: ...

    def virtual_memory(self) -> _VirtualMemory: ...


psutil = cast(_PsutilModule, importlib.import_module('psutil'))

MEBIBYTE = 1024**2


class RssSampler:
    """Sample parent RSS and the sum of descendant RSS in background.

    The aggregate is a sum of process RSS values, not cgroup memory or unique
    resident physical memory; shared pages can be counted more than once.
    """

    def __init__(self, interval_seconds: float = 0.01) -> None:
        """Create a sampler with the documented 10 ms default interval."""
        self.interval_seconds = interval_seconds
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.parent_before_bytes = 0
        self.parent_peak_bytes = 0
        self.aggregate_peak_bytes = 0
        self.child_count_peak = 0
        self.worker_pids_observed: set[int] = set()

    def start(self) -> None:
        """Start collection before the measured product operation."""
        parent_bytes, total_bytes, pids = self._read_rss()
        self.parent_before_bytes = parent_bytes
        self.parent_peak_bytes = parent_bytes
        self.aggregate_peak_bytes = total_bytes
        self.child_count_peak = len(pids)
        self.worker_pids_observed.update(pids)
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        """Stop collection and return the final parent RSS measurement."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        parent_bytes, total_bytes, pids = self._read_rss()
        self.parent_peak_bytes = max(self.parent_peak_bytes, parent_bytes)
        self.aggregate_peak_bytes = max(self.aggregate_peak_bytes, total_bytes)
        self.child_count_peak = max(self.child_count_peak, len(pids))
        self.worker_pids_observed.update(pids)
        return parent_bytes

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            parent_bytes, total_bytes, pids = self._read_rss()
            self.parent_peak_bytes = max(self.parent_peak_bytes, parent_bytes)
            self.aggregate_peak_bytes = max(
                self.aggregate_peak_bytes, total_bytes
            )
            self.child_count_peak = max(self.child_count_peak, len(pids))
            self.worker_pids_observed.update(pids)

    def _read_rss(self) -> tuple[int, int, list[int]]:
        """Return (parent_rss_bytes, aggregate_rss_bytes, child_pids)."""
        try:
            parent_rss = int(self._process.memory_info().rss)
        except psutil.Error:
            parent_rss = self.parent_peak_bytes

        total_rss = parent_rss
        child_pids: list[int] = []
        try:
            children = self._process.children(recursive=True)
            for child in children:
                try:
                    child_pids.append(child.pid)
                    total_rss += int(child.memory_info().rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return parent_rss, total_rss, child_pids

    def to_record_metrics(self, parent_after_bytes: int) -> dict[str, Any]:
        """Convert observed memory measurements into record fields."""
        parent_before_mib = self.parent_before_bytes / MEBIBYTE
        parent_peak_mib = self.parent_peak_bytes / MEBIBYTE
        parent_after_mib = parent_after_bytes / MEBIBYTE
        aggregate_peak_mib = self.aggregate_peak_bytes / MEBIBYTE
        return {
            'rss_before_mib': parent_before_mib,
            'rss_peak_mib': parent_peak_mib,
            'rss_after_mib': parent_after_mib,
            'parent_rss_before_mib': parent_before_mib,
            'parent_rss_peak_mib': parent_peak_mib,
            'parent_rss_after_mib': parent_after_mib,
            'aggregate_rss_peak_mib': aggregate_peak_mib,
            'child_process_count_peak': self.child_count_peak,
            'worker_pids_observed': sorted(self.worker_pids_observed),
        }
