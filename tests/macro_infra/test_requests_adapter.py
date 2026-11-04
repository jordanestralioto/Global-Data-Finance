from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from globaldatafinance.macro_exceptions import (
    DiskFullError,
    FileWriteError,
    PathPermissionError,
    SecurityError,
)
from globaldatafinance.macro_infra import RequestsAdapter
from tests.support.fake_http import FakeResponse, install_fake_http_client

pytestmark = pytest.mark.unit


def _staging_files(target: Path) -> list[Path]:
    return sorted(target.parent.glob(f'.{target.name}.*.part'))


class TestRequestsAdapterInitialization:
    def test_initialization_with_defaults(self):
        adapter = RequestsAdapter()
        assert adapter.timeout == 60.0
        assert adapter.max_redirects == 5
        assert adapter.verify is True
        assert adapter.http2 is False
        assert adapter.follow_redirects is True

    def test_initialization_with_custom_params(self):
        adapter = RequestsAdapter(
            timeout=120.0, max_redirects=10, verify=False, http2=True
        )
        assert adapter.timeout == 120.0
        assert adapter.max_redirects == 10
        assert adapter.verify is False
        assert adapter.http2 is True

    def test_initialization_can_disable_redirect_following(self):
        adapter = RequestsAdapter(follow_redirects=False)

        assert adapter.follow_redirects is False

    def test_initialization_without_default_headers(self):
        adapter = RequestsAdapter()

        assert adapter.default_headers is None

    def test_initialization_with_default_headers(self):
        adapter = RequestsAdapter(
            default_headers={'User-Agent': 'test-client/1.0'}
        )

        assert adapter.default_headers == {'User-Agent': 'test-client/1.0'}


class TestRequestsAdapterAsyncMethods:
    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_async_head_request_success(self, mock_client_class):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': '1024'}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = RequestsAdapter()
        response = await adapter.async_head('https://example.com')

        assert response.status_code == 200
        assert response.headers['content-length'] == '1024'
        mock_client.head.assert_called_once()

    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_async_head_with_custom_headers(self, mock_client_class):
        mock_response = Mock()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = RequestsAdapter()
        headers = {'Authorization': 'Bearer token'}
        await adapter.async_head('https://example.com', headers=headers)

        call_args = mock_client.head.call_args
        assert httpx.Headers(call_args[1]['headers']) == httpx.Headers(
            {'Authorization': 'Bearer token', 'Accept-Encoding': 'identity'}
        )
        assert headers == {'Authorization': 'Bearer token'}

    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_async_head_requests_identity_encoding_by_default(
        self, mock_client_class
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = Mock()
        mock_client_class.return_value = mock_client

        await RequestsAdapter().async_head('https://example.com')

        assert mock_client.head.call_args.kwargs['headers'] == {
            'accept-encoding': 'identity'
        }

    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_async_head_propagates_configured_user_agent(
        self, mock_client_class
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = Mock()
        mock_client_class.return_value = mock_client

        adapter = RequestsAdapter(
            default_headers={'User-Agent': 'configured-client/1.0'}
        )
        await adapter.async_head('https://example.com')

        assert httpx.Headers(
            mock_client.head.call_args.kwargs['headers']
        ) == httpx.Headers(
            {
                'User-Agent': 'configured-client/1.0',
                'Accept-Encoding': 'identity',
            }
        )

    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_request_headers_override_default_headers(
        self, mock_client_class
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = Mock()
        mock_client_class.return_value = mock_client

        adapter = RequestsAdapter(
            default_headers={
                'User-Agent': 'configured-client/1.0',
                'Accept': 'application/octet-stream',
            }
        )
        await adapter.async_head(
            'https://example.com',
            headers={'user-agent': 'per-request-client/2.0'},
        )

        assert httpx.Headers(
            mock_client.head.call_args.kwargs['headers']
        ) == httpx.Headers(
            {
                'Accept': 'application/octet-stream',
                'User-Agent': 'per-request-client/2.0',
                'Accept-Encoding': 'identity',
            }
        )

    @pytest.mark.asyncio
    @patch('globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient')
    async def test_async_head_with_custom_timeout(self, mock_client_class):
        mock_response = Mock()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = RequestsAdapter()
        await adapter.async_head('https://example.com', timeout=10.0)

        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args
        assert call_args[1]['timeout'] == 10.0


class TestRequestsAdapterDownload:
    @pytest.mark.asyncio
    async def test_valid_download_replaces_old_target_without_staging_left(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        target.write_bytes(b'old archive')
        payload = b'new archive contents'
        response = FakeResponse(
            'https://example.com/file.zip',
            [payload[:5], payload[5:]],
            headers={'content-length': str(len(payload))},
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        await RequestsAdapter().async_download_file(
            'https://example.com/file.zip', str(target), chunk_size=5
        )

        assert target.read_bytes() == payload
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_staging_download_does_not_promote_target(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        payload = b'staged archive contents'
        response = FakeResponse('https://example.com/file.zip', [payload])
        install_fake_http_client(monkeypatch, lambda _url: response)

        staging_path = await RequestsAdapter().async_download_to_staging_file(
            'https://example.com/file.zip', str(target)
        )
        try:
            assert staging_path.parent == tmp_path
            assert staging_path.name.startswith(f'.{target.name}.')
            assert staging_path.suffix == '.part'
            assert staging_path.read_bytes() == payload
            assert target.read_bytes() == old_bytes
        finally:
            staging_path.unlink(missing_ok=True)

        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_content_length_limit_preserves_old_zip_and_cleans_staging(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        response = FakeResponse(
            'https://example.com/file.zip',
            [b'new archive'],
            headers={'content-length': '11'},
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        with pytest.raises(SecurityError, match='Content-Length exceeds'):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target), max_bytes=10
            )

        assert target.read_bytes() == old_bytes
        assert response.iterated is False
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_stream_limit_preserves_old_target_and_cleans_staging(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        response = FakeResponse(
            'https://example.com/file.zip', [b'abcd', b'efgh']
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        with pytest.raises(SecurityError, match='download exceeds'):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target), max_bytes=6
            )

        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_http_failure_preserves_old_target_and_cleans_staging(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        response = FakeResponse(
            'https://example.com/file.zip', [], status_code=503
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        with pytest.raises(httpx.HTTPStatusError):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target)
            )

        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('write_error', 'expected_error'),
        [
            ('No space left on device', DiskFullError),
            ('Permission denied', PathPermissionError),
            ('I/O error', FileWriteError),
        ],
    )
    async def test_write_failure_preserves_old_target_and_cleans_staging(
        self, tmp_path, monkeypatch, write_error, expected_error
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        response = FakeResponse(
            'https://example.com/file.zip', [b'new archive']
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        original_open = Path.open

        class FailingWriteFile:
            def __init__(self, file_handle: Any):
                self.file_handle = file_handle

            def __enter__(self) -> FailingWriteFile:
                self.file_handle.__enter__()
                return self

            def __exit__(self, *args: object) -> Any:
                return self.file_handle.__exit__(*args)

            def write(self, _chunk: bytes) -> int:
                raise OSError(write_error)

        def open_with_failure(path: Path, *args: Any, **kwargs: Any) -> Any:
            file_handle = original_open(path, *args, **kwargs)
            if path.name.startswith(f'.{target.name}.'):
                return FailingWriteFile(file_handle)
            return file_handle

        monkeypatch.setattr(Path, 'open', open_with_failure)

        with pytest.raises(expected_error):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target)
            )

        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_promotion_failure_cleans_staging_and_preserves_old_target(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        payload = b'new archive contents'
        response = FakeResponse(
            'https://example.com/file.zip',
            [payload],
            headers={'content-length': str(len(payload))},
        )
        install_fake_http_client(monkeypatch, lambda _url: response)
        original_replace = Path.replace

        def fail_staging_replace(source: Path, destination: Path) -> Path:
            if source.name.startswith(f'.{target.name}.'):
                raise OSError('promotion failed')
            return cast(Path, original_replace(source, destination))

        monkeypatch.setattr(Path, 'replace', fail_staging_replace)

        with pytest.raises(OSError, match='promotion failed'):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target)
            )

        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_cancellation_cleans_staging_and_preserves_old_target(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'old archive'
        target.write_bytes(old_bytes)
        started = asyncio.Event()

        class BlockingResponse(FakeResponse):
            async def aiter_bytes(self, *, chunk_size: int):
                del chunk_size
                yield b'partial new archive'
                started.set()
                await asyncio.Future()

        response = BlockingResponse(
            'https://example.com/file.zip', [b'ignored by override']
        )
        install_fake_http_client(monkeypatch, lambda _url: response)

        task = asyncio.create_task(
            RequestsAdapter().async_download_to_staging_file(
                'https://example.com/file.zip', str(target)
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    @pytest.mark.asyncio
    async def test_invalid_byte_limit_has_no_filesystem_or_network_side_effect(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        target.write_bytes(b'old archive')
        called = False

        def response_factory(_url: str) -> FakeResponse:
            nonlocal called
            called = True
            return FakeResponse(_url, [b'never used'])

        install_fake_http_client(monkeypatch, response_factory)

        with pytest.raises(ValueError, match='max_bytes'):
            await RequestsAdapter().async_download_file(
                'https://example.com/file.zip', str(target), max_bytes=0
            )

        assert called is False
        assert target.read_bytes() == b'old archive'
        assert _staging_files(target) == []
