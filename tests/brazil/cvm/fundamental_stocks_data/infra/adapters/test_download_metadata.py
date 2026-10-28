"""GET validates its own transfer without changing adapter configuration."""

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    AsyncDownloadAdapterCVM,
)
from tests.support.fake_http import install_mock_http_transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _archive_bytes() -> bytes:
    """Create a complete regulatory ZIP without any external source."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('data.csv', b'id;value\n1;valid\n')
    return buffer.getvalue()


@pytest.mark.parametrize('size_header', ['valid', 'missing', 'invalid'])
async def test_completed_get_uses_only_its_own_optional_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    size_header: str,
) -> None:
    """A later source version cannot invalidate a completed transfer."""
    payload = _archive_bytes()
    methods: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == 'HEAD':
            return httpx.Response(
                200, headers={'content-length': str(len(payload) + 1)}
            )
        headers = {'content-length': str(len(payload))}
        if size_header == 'invalid':
            headers['content-length'] = 'invalid'
        response = httpx.Response(200, content=payload, headers=headers)
        if size_header == 'missing':
            del response.headers['content-length']
        return response

    install_mock_http_transport(monkeypatch, respond)
    adapter = AsyncDownloadAdapterCVM(None)
    result = await adapter.async_download_docs(
        [('https://example.test/source.zip', 'DFP', '2024', str(tmp_path))]
    )

    assert result.successful_downloads == ['DFP_2024']
    assert result.failed_downloads == {}
    assert methods == ['GET']
    assert (tmp_path / 'source.zip').read_bytes() == payload
    assert sorted(path.name for path in tmp_path.iterdir()) == ['source.zip']


@pytest.mark.parametrize('size_delta', [-1, 1])
async def test_get_size_mismatch_preserves_existing_zip_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    size_delta: int,
) -> None:
    """Even a readable ZIP is rejected if its own GET length disagrees."""
    payload = _archive_bytes()
    target = tmp_path / 'source.zip'
    target.write_bytes(b'previous caller-owned ZIP')

    def respond(request: httpx.Request) -> httpx.Response:
        length = len(payload) + (size_delta if request.method == 'GET' else 0)
        return httpx.Response(
            200, content=payload, headers={'content-length': str(length)}
        )

    install_mock_http_transport(monkeypatch, respond)
    result = await AsyncDownloadAdapterCVM(
        None, max_retries=0
    ).async_download_docs(
        [('https://example.test/source.zip', 'DFP', '2024', str(tmp_path))]
    )

    assert result.successful_downloads == []
    assert 'Content-Length' in result.failed_downloads['DFP_2024']
    assert target.read_bytes() == b'previous caller-owned ZIP'
    assert list(tmp_path.iterdir()) == [target]


async def test_get_size_mismatch_retries_with_metadata_from_the_new_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial transfer retries and publishes only the complete attempt."""
    payload = _archive_bytes()
    get_attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal get_attempts
        if request.method == 'GET':
            get_attempts += 1
        size = len(payload) + (get_attempts == 1)
        return httpx.Response(
            200, content=payload, headers={'content-length': str(size)}
        )

    install_mock_http_transport(monkeypatch, respond)
    adapter = AsyncDownloadAdapterCVM(None, max_retries=1, initial_backoff=0)
    result = await adapter.async_download_docs(
        [('https://example.test/source.zip', 'DFP', '2024', str(tmp_path))]
    )

    assert get_attempts == 2
    assert result.successful_downloads == ['DFP_2024']
    assert result.failed_downloads == {}
    assert (tmp_path / 'source.zip').read_bytes() == payload
    assert not list(tmp_path.glob('*.part'))


async def test_automatic_extraction_keeps_adapter_configuration_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Creating a default extractor does not configure later operations."""
    payload = _archive_bytes()
    install_mock_http_transport(
        monkeypatch, lambda _request: httpx.Response(200, content=payload)
    )
    adapter = AsyncDownloadAdapterCVM(None)
    head = AsyncMock(side_effect=AssertionError('unexpected HEAD'))
    monkeypatch.setattr(adapter.requests_adapter, 'async_head', head)
    automatic = tmp_path / 'automatic'
    disabled = tmp_path / 'disabled'
    automatic.mkdir()
    disabled.mkdir()

    extracted = await adapter.async_download_docs(
        [('https://example.test/source.zip', 'DFP', '2024', str(automatic))],
        automatic_extractor=True,
    )
    downloaded = await adapter.async_download_docs(
        [('https://example.test/source.zip', 'DFP', '2024', str(disabled))],
        automatic_extractor=False,
    )

    assert (
        extracted.successful_downloads
        == downloaded.successful_downloads
        == ['DFP_2024']
    )
    assert (automatic / 'data.parquet').is_file()
    assert sorted(path.name for path in disabled.iterdir()) == ['source.zip']
    assert adapter.file_extractor_repository is None
    assert adapter.automatic_extractor is False
    head.assert_not_awaited()
