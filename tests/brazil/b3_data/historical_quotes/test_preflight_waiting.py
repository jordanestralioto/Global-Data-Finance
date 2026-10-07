"""Prove preflight polling preserves completed results and worker errors."""

from concurrent.futures import Future, TimeoutError
from typing import cast
from unittest.mock import Mock

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    AnnualResult,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from globaldatafinance.brazil.b3_data.historical_quotes.models import (
    ValidatedCotahistSource,
)
from globaldatafinance.brazil.b3_data.historical_quotes.preflight import (
    AnnualFailure,
    await_preflight,
)

pytestmark = pytest.mark.unit

_Outcome = AnnualResult | AnnualFailure


class _CompletionAfterPollTimeout(Future[_Outcome]):
    """Complete after a real poll timeout, before the caller checks done."""

    def __init__(self, completion: _Outcome) -> None:
        super().__init__()
        self.completion = completion

    def result(self, timeout: float | None = None) -> _Outcome:
        if not self.done():
            try:
                super().result(timeout=0)
            except TimeoutError:
                self.set_result(self.completion)
                raise
        return super().result(timeout=timeout)


def test_completed_result_survives_poll_timeout_boundary() -> None:
    source = cast(ValidatedCotahistSource, Mock(spec=ValidatedCotahistSource))
    expected: AnnualResult = (source, None)
    future = _CompletionAfterPollTimeout(expected)

    assert await_preflight(future) is expected
    assert future.done()


def test_completed_failure_keeps_typed_cause_after_poll_timeout() -> None:
    error = CotahistCatalogError('invalid annual quotation')
    cause = ValueError('invalid trading date')
    error.__cause__ = cause
    failure = AnnualFailure.capture(error)
    error.__cause__ = None
    future = _CompletionAfterPollTimeout(failure)

    with pytest.raises(CotahistCatalogError) as observed:
        await_preflight(future)

    assert observed.value is error
    assert observed.value.__cause__ is cause
    assert future.done()


def test_worker_timeout_is_preserved_as_the_original_exception() -> None:
    future: Future[_Outcome] = Future()
    error = TimeoutError('annual worker timed out')
    future.set_exception(error)

    with pytest.raises(TimeoutError) as observed:
        await_preflight(future)

    assert observed.value is error
