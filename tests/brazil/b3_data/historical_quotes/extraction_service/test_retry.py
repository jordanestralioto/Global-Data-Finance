"""Unit proof for the narrow B3 unpublished-I/O retry policy."""

from __future__ import annotations

import errno

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.macro_exceptions import (
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)

pytestmark = pytest.mark.unit

retry = extraction_service.retry


@pytest.mark.parametrize(
    'error_number', [errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT]
)
def test_only_documented_transient_os_errors_are_retryable(
    error_number: int,
) -> None:
    """Retry classification is intentionally narrower than generic OSError."""
    assert retry.is_retryable_io_error(OSError(error_number, 'temporary'))
    assert not retry.is_retryable_io_error(OSError(errno.ENOSPC, 'full'))
    assert not retry.is_retryable_io_error(DiskFullError('output.parquet'))
    assert not retry.is_retryable_io_error(
        ExtractionError('source', 'invalid')
    )


def test_transient_operation_gets_three_total_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The policy sleeps only between the two permitted retry attempts."""
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError(errno.EAGAIN, 'again')
        return 'complete'

    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.'
        'extraction_service.retry.time.sleep',
        delays.append,
    )

    assert retry.retry_unpublished_io(operation) == 'complete'
    assert attempts == 3
    assert delays == [0.25, 0.5]


@pytest.mark.parametrize(
    'error',
    [
        ValueError('invalid unpublished operation'),
        MemoryError('memory pressure is not transient I/O'),
        OSError(errno.ENOSPC, 'no space left on device'),
        ParquetWriteError('output.parquet', 'permanent write failure'),
    ],
)
def test_permanent_operation_failure_is_attempted_once(
    error: Exception,
) -> None:
    """Permanent failures are re-raised without a duplicate write attempt."""
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(type(error)):
        retry.retry_unpublished_io(operation)

    assert attempts == 1
