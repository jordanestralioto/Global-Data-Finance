"""Calculate retry eligibility and jittered exponential backoff."""

from secrets import SystemRandom
from typing import ClassVar

from ...macro_exceptions import (
    DiskFullError,
    DownloadTimeoutError,
    NetworkError,
    PathPermissionError,
)


class RetryStrategy:
    """Handles retry logic and backoff calculations.

    This class determines which exceptions warrant a retry based on their type
    and error message patterns. It uses the application's standard exception
    hierarchy (macro_exceptions) to avoid dependencies on external libraries.
    """

    _RETRYABLE_KEYWORDS: ClassVar[list[str]] = [
        'timeout',
        'connection refused',
        'connection reset',
        'connection aborted',
        'temporarily',
        'unavailable',
        'try again',
    ]

    def __init__(
        self, initial_backoff: float, max_backoff: float, multiplier: float
    ):
        """Initialize the exponential backoff parameters."""
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.multiplier = multiplier

    def is_retryable(self, exception: Exception) -> bool:
        """Determines if an exception warrants a retry.

        An exception is retryable if:
        - It is a NetworkError or DownloadTimeoutError (transient network
          issues)
        - Its error message contains retryable keywords

        Non-retryable exceptions: PathPermissionError, DiskFullError, and
        ValueError.

        Args:
            exception: The exception to evaluate

        Returns:
            True if the exception should trigger a retry, False otherwise
        """
        if isinstance(
            exception, (PathPermissionError, DiskFullError, ValueError)
        ):
            return False

        if isinstance(exception, (NetworkError, DownloadTimeoutError)):
            return True

        # Fallback: check error message for known retryable keywords
        error_msg = str(exception).lower()
        return any(kw in error_msg for kw in self._RETRYABLE_KEYWORDS)

    def calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff with bounded multiplicative jitter.

        Applies a uniform random multiplier in ``[0.5, 1.5]`` to the
        deterministic exponential value before clamping to
        ``max_backoff``. The expected value matches the deterministic
        formula (E[U(0.5, 1.5)] = 1.0) but the spread avoids
        thundering-herd retries when multiple concurrent downloads
        fail in lockstep.
        """
        deterministic = self.initial_backoff * (self.multiplier**retry_count)
        jittered = deterministic * SystemRandom().uniform(0.5, 1.5)
        return min(jittered, self.max_backoff)
