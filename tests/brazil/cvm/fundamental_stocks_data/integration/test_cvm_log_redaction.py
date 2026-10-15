"""CVM metadata failure logs redact caller-supplied URL credentials."""

from __future__ import annotations

import httpx
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_validation,
)
from globaldatafinance.core.logging_config import StructuredFormatter
from globaldatafinance.macro_infra import RequestsAdapter
from tests.support.fake_http import install_mock_http_transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    'url',
    [
        '//user:synthetic-password@example.test/file?year=2024',
        'https://example.test/file?code=synthetic-code&year=2024',
        'https://example.test/file?state=synthetic-state&year=2024',
        'https://example.test/file?%63ode=synthetic-code&year=2024',
        'https://example.test/file?%73tate=synthetic-state&year=2024',
    ],
)
async def test_cvm_metadata_failure_logs_redact_url_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    url: str,
) -> None:
    """A real HTTPX failure passes through the library's warning formatter."""

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('synthetic transport outage', request=request)

    install_mock_http_transport(monkeypatch, fail)

    with caplog.at_level('WARNING'):
        result = await download_validation.get_content_length(
            RequestsAdapter(), url
        )

    records = [
        record
        for record in caplog.records
        if 'Failed to get Content-Length' in record.getMessage()
    ]
    assert result is None
    assert len(records) == 1
    formatted = StructuredFormatter('%(message)s').format(records[0])
    assert 'synthetic-password' not in formatted
    assert 'synthetic-code' not in formatted
    assert 'synthetic-state' not in formatted
    assert '[REDACTED]' in formatted
    assert 'year=2024' in formatted
