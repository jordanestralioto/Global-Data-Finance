"""Narrow retry policy for unpublished B3 filesystem work."""

from __future__ import annotations

import errno
import time
from collections.abc import Callable

from .....macro_exceptions import DiskFullError, ExtractionError

_TRANSIENT_ERRNOS = frozenset({errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT})
_DELAYS_SECONDS = (0.25, 0.5)


def is_retryable_io_error(error: BaseException) -> bool:
    """Return true only for a transient OS error outside integrity failures."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ExtractionError, DiskFullError)):
            return False
        if isinstance(current, OSError) and current.errno in _TRANSIENT_ERRNOS:
            return True
        cause = current.__cause__
        current = cause if isinstance(cause, BaseException) else None
    return False


def retry_unpublished_io[Result](operation: Callable[[], Result]) -> Result:
    """Retry only documented transient OS failures for three total attempts."""
    for delay in (*_DELAYS_SECONDS, None):
        try:
            return operation()
        except Exception as error:
            if delay is None or not is_retryable_io_error(error):
                raise
            time.sleep(delay)
    raise RuntimeError('Unreachable retry state')
