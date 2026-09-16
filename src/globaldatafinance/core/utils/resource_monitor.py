"""Monitor process resources for extraction workloads."""

import gc
import os
import platform
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import psutil

from ..logging_config import get_logger

logger = get_logger(__name__)


class ResourceState(Enum):
    """Represents the current state of system resources."""

    HEALTHY = 'healthy'
    WARNING = 'warning'
    CRITICAL = 'critical'
    EXHAUSTED = 'exhausted'


_STATE_SEVERITY: dict[ResourceState, int] = {
    ResourceState.HEALTHY: 0,
    ResourceState.WARNING: 1,
    ResourceState.CRITICAL: 2,
    ResourceState.EXHAUSTED: 3,
}


@dataclass
class ResourceLimits:
    """Configuration for resource limits and thresholds."""

    memory_warning_threshold: float = 70.0
    memory_critical_threshold: float = 85.0
    memory_exhausted_threshold: float = 95.0
    cpu_warning_threshold: float = 80.0
    cpu_critical_threshold: float = 90.0
    min_free_memory_mb: int = 100
    auto_gc_on_warning: bool = True
    circuit_breaker_cooldown_seconds: int = 10
    circuit_breaker_enabled: bool = True


class ResourceMonitor:
    """Monitor system resources and manage memory/CPU constraints.

    This class provides real-time resource monitoring with configurable
    thresholds and automatic mitigation strategies.

    Example:
        >>> monitor = ResourceMonitor()
        >>> state = monitor.check_resources()
        >>> if state == ResourceState.CRITICAL:
        ...     # Reduce batch size, pause processing, etc.
        ...     pass
    """

    _instance: Optional['ResourceMonitor'] = None
    _lock = threading.Lock()

    def __new__(cls, *_args: object, **_kwargs: object) -> 'ResourceMonitor':
        """Singleton pattern to ensure only one monitor instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        """Initialize resource monitor.

        Args:
            limits: Optional custom resource limits. Uses defaults if None.
        """
        if not hasattr(self, '_initialized'):
            self._initialize(limits)

    @classmethod
    def create_isolated(
        cls, limits: ResourceLimits | None = None
    ) -> 'ResourceMonitor':
        """Create local limits without changing the singleton monitor."""
        monitor = object.__new__(cls)
        monitor._initialize(limits)
        return monitor

    def _initialize(self, limits: ResourceLimits | None) -> None:
        """Initialize one monitor instance, singleton-backed or isolated."""
        self.limits = limits or ResourceLimits()
        self._circuit_breaker_active = False
        self._circuit_breaker_triggered_at: float | None = None
        self._last_gc_time: float = 0
        self._gc_cooldown_seconds: int = 5

        self._log_system_info()
        self._initialized = True

    def _log_system_info(self) -> None:
        """Log system information for debugging."""
        info = {
            'platform': platform.system(),
            'python_version': platform.python_version(),
            'cpu_count': os.cpu_count() or 1,
        }

        memory = psutil.virtual_memory()
        info['total_ram_gb'] = f'{memory.total / (1024**3):.2f}'
        info['available_ram_gb'] = f'{memory.available / (1024**3):.2f}'

        logger.info('ResourceMonitor initialized', extra=info)

    def check_resources(self) -> ResourceState:
        """Check current resource state.

        Returns:
            Current resource state (HEALTHY, WARNING, CRITICAL, or EXHAUSTED)
        """
        if self._circuit_breaker_active:
            if self._should_reset_circuit_breaker():
                self._reset_circuit_breaker()
            else:
                return ResourceState.EXHAUSTED

        try:
            memory_state = self._check_memory()
            cpu_state = self._check_cpu()

            if ResourceState.EXHAUSTED in (memory_state, cpu_state):
                self._trigger_circuit_breaker()
                return ResourceState.EXHAUSTED
            if ResourceState.CRITICAL in (memory_state, cpu_state):
                return ResourceState.CRITICAL
            if ResourceState.WARNING in (memory_state, cpu_state):
                if self.limits.auto_gc_on_warning:
                    self._maybe_force_gc()
                return ResourceState.WARNING
            return ResourceState.HEALTHY

        except Exception as e:
            logger.error(f'Error checking resources: {e}', exc_info=True)
            return ResourceState.CRITICAL

    def _check_memory(self) -> ResourceState:
        """Check memory usage state.

        Returns:
            Resource state based on memory usage
        """
        memory = psutil.virtual_memory()
        percent_used = memory.percent
        free_mb = memory.available / (1024**2)

        if free_mb < self.limits.min_free_memory_mb:
            logger.error(
                f'Memory exhausted: {free_mb:.1f}MB free '
                f'(minimum: {self.limits.min_free_memory_mb}MB)'
            )
            return ResourceState.EXHAUSTED

        if percent_used >= self.limits.memory_exhausted_threshold:
            logger.error(f'Memory exhausted: {percent_used:.1f}% used')
            return ResourceState.EXHAUSTED
        if percent_used >= self.limits.memory_critical_threshold:
            logger.warning(f'Memory critical: {percent_used:.1f}% used')
            return ResourceState.CRITICAL
        if percent_used >= self.limits.memory_warning_threshold:
            logger.info(f'Memory warning: {percent_used:.1f}% used')
            return ResourceState.WARNING
        return ResourceState.HEALTHY

    def _check_cpu(self) -> ResourceState:
        """Check CPU usage state.

        Returns:
            Resource state based on CPU usage
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent >= self.limits.cpu_critical_threshold:
            logger.warning(f'CPU critical: {cpu_percent:.1f}% used')
            return ResourceState.CRITICAL
        if cpu_percent >= self.limits.cpu_warning_threshold:
            logger.info(f'CPU warning: {cpu_percent:.1f}% used')
            return ResourceState.WARNING
        return ResourceState.HEALTHY

    def get_safe_worker_count(self, max_workers: int | None = None) -> int:
        """Calculate safe number of workers based on available resources.

        Args:
            max_workers: Maximum desired workers (None = CPU count)

        Returns:
            Safe number of workers (at least 1)
        """
        cpu_count = os.cpu_count() or 1

        if max_workers is None:
            max_workers = cpu_count

        memory_state = self._check_memory()

        if memory_state == ResourceState.EXHAUSTED:
            safe_count = 1
        elif memory_state == ResourceState.CRITICAL:
            safe_count = min(2, cpu_count)
        elif memory_state == ResourceState.WARNING:
            safe_count = max(1, max_workers // 2)
        else:
            safe_count = min(max_workers, cpu_count)

        if safe_count < max_workers:
            logger.info(
                f'Reduced worker count from {max_workers} to {safe_count} '
                f'due to resource constraints'
            )

        return safe_count

    def get_safe_batch_size(self, desired_batch_size: int) -> int:
        """Calculate safe batch size based on available memory.

        Args:
            desired_batch_size: Desired batch size

        Returns:
            Safe batch size (at least 1000)
        """
        memory_state = self._check_memory()
        min_batch_size = 1000

        if memory_state == ResourceState.EXHAUSTED:
            safe_size = min_batch_size
        elif memory_state == ResourceState.CRITICAL:
            safe_size = max(min_batch_size, desired_batch_size // 4)
        elif memory_state == ResourceState.WARNING:
            safe_size = max(min_batch_size, desired_batch_size // 2)
        else:
            safe_size = desired_batch_size

        if safe_size < desired_batch_size:
            logger.info(
                f'Reduced batch size from {desired_batch_size} to {safe_size} '
                f'due to memory constraints'
            )

        return safe_size

    def _maybe_force_gc(self) -> None:
        """Force garbage collection if cooldown period has passed."""
        current_time = time.time()
        if current_time - self._last_gc_time >= self._gc_cooldown_seconds:
            logger.debug('Forcing garbage collection to free memory')
            gc.collect()
            self._last_gc_time = current_time

    def _trigger_circuit_breaker(self) -> None:
        """Trigger circuit breaker due to resource exhaustion."""
        if not self.limits.circuit_breaker_enabled:
            return

        self._circuit_breaker_active = True
        self._circuit_breaker_triggered_at = time.time()

        logger.critical(
            f'Circuit breaker triggered! Processing paused for '
            f'{self.limits.circuit_breaker_cooldown_seconds} seconds'
        )

        # Force aggressive garbage collection
        gc.collect()

    def _should_reset_circuit_breaker(self) -> bool:
        """Check if circuit breaker cooldown has passed.

        Returns:
            True if circuit breaker should be reset
        """
        if (
            not self._circuit_breaker_active
            or self._circuit_breaker_triggered_at is None
        ):
            return False

        elapsed = time.time() - self._circuit_breaker_triggered_at
        return elapsed >= self.limits.circuit_breaker_cooldown_seconds

    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker after cooldown."""
        logger.info('Circuit breaker reset - resuming processing')
        self._circuit_breaker_active = False
        self._circuit_breaker_triggered_at = None

    def get_process_memory_mb(self) -> float:
        """Get memory used by current process in MB.

        Returns:
            Memory used by the current process in MB
        """
        try:
            return float(psutil.Process().memory_info().rss / (1024**2))
        except Exception as e:
            logger.error(f'Error getting process memory: {e}', exc_info=True)
            return 0.0

    def wait_for_resources(
        self,
        required_state: ResourceState = ResourceState.WARNING,
        timeout_seconds: int = 60,
    ) -> bool:
        """Wait until resources are in acceptable state.

        Args:
            required_state: Maximum acceptable state (default: WARNING)
            timeout_seconds: Maximum time to wait (default: 60s)

        Returns:
            True if resources became available, False if timeout
        """
        start_time = time.time()
        check_interval = 1  # Check every second

        while time.time() - start_time < timeout_seconds:
            current_state = self.check_resources()

            # Check if state is acceptable (lower or equal severity)
            if (
                _STATE_SEVERITY[current_state]
                <= _STATE_SEVERITY[required_state]
            ):
                return True

            logger.debug(
                f'Waiting for resources... Current state: '
                f'{current_state.value}, '
                f'Required: {required_state.value}'
            )

            time.sleep(check_interval)

        logger.warning(f'Resource wait timeout after {timeout_seconds}s')
        return False
