"""CVM transfer failure logs redact caller-supplied URL credentials."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
)
from globaldatafinance.core.logging_config import StructuredFormatter
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
async def test_cvm_transfer_failure_logs_redact_url_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    url: str,
) -> None:
    """A real HTTPX failure passes through the library's warning formatter."""

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f'synthetic transport outage: {url}', request=request
        )

    install_mock_http_transport(monkeypatch, fail)

    with caplog.at_level('ERROR'):
        success, error = await AsyncDownloadAdapterCVM(
            None, max_retries=0
        )._download_with_retry(
            url, str(tmp_path / 'source.zip'), 'DFP', '2024'
        )

    records = [
        record
        for record in caplog.records
        if 'Download failed' in record.getMessage()
    ]
    assert success is False
    assert error is not None
    assert len(records) == 1
    formatted = StructuredFormatter('%(message)s').format(records[0])
    assert 'synthetic-password' not in formatted
    assert 'synthetic-code' not in formatted
    assert 'synthetic-state' not in formatted
    assert '[REDACTED]' in formatted
    assert 'year=2024' in formatted
