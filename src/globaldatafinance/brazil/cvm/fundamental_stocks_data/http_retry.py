"""Translate CVM transport failures without retrying permanent HTTP errors."""

from __future__ import annotations

import httpx

from ....core import RetryStrategy
from ....macro_exceptions import DownloadTimeoutError, NetworkError

_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def classify_download_error(
    error: Exception,
    document_key: str,
    timeout: float,
    strategy: RetryStrategy,
) -> tuple[Exception, bool]:
    """Retain diagnostic types and decide status retries before translation."""
    if isinstance(error, httpx.HTTPStatusError):
        return (
            NetworkError(document_key, f'{type(error).__name__}: {error}'),
            error.response.status_code in _RETRYABLE_HTTP_STATUSES,
        )
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        translated: Exception = DownloadTimeoutError(document_key, timeout)
    elif isinstance(error, (httpx.RequestError, ConnectionError)):
        translated = NetworkError(
            document_key, f'{type(error).__name__}: {error}'
        )
    else:
        translated = error
    return translated, strategy.is_retryable(translated)
