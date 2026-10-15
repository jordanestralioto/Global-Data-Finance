"""CVM HTTP retries distinguish permanent statuses from transient failures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    http as cvm_http,
)
from tests.support.fake_http import install_mock_http_transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize('status', [400, 401, 403, 404, 410, 501, 505])
async def test_permanent_http_status_never_waits_or_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """Permanent errors keep their status and leave the existing ZIP intact."""
    attempts = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status)

    install_mock_http_transport(monkeypatch, respond)
    sleep = AsyncMock()
    monkeypatch.setattr(cvm_http.asyncio, 'sleep', sleep)
    target = tmp_path / 'source.zip'
    target.write_bytes(b'previous archive')
    adapter = AsyncDownloadAdapterCVM(None)

    success, error = await adapter._download_with_retry(
        'https://example.test/unavailable.zip', str(target), 'DFP', '2024'
    )

    assert success is False
    assert error is not None
    assert 'NetworkError' in error and str(status) in error
    assert attempts == 1
    sleep.assert_not_awaited()
    assert target.read_bytes() == b'previous archive'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504])
async def test_transient_http_status_uses_the_configured_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """Transient HTTP errors retain three attempts for two allowed retries."""
    attempts = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status)

    install_mock_http_transport(monkeypatch, respond)
    sleep = AsyncMock()
    monkeypatch.setattr(cvm_http.asyncio, 'sleep', sleep)
    adapter = AsyncDownloadAdapterCVM(None, max_retries=2)
    target = tmp_path / 'source.zip'

    success, error = await adapter._download_with_retry(
        'https://example.test/source.zip', str(target), 'DFP', '2024'
    )

    assert success is False
    assert error is not None and str(status) in error
    assert attempts == 3
    assert sleep.await_count == 2
    assert list(tmp_path.iterdir()) == []
