"""Real HTTPX streaming and redirects enforce budgets and credential scope."""

from __future__ import annotations

import gzip
import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from globaldatafinance.macro_exceptions import SecurityError
from globaldatafinance.macro_infra import RequestsAdapter
from tests.support.fake_http import install_mock_http_transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class ObservedStream(httpx.AsyncByteStream):
    """Observe consumption and closure at the external transport boundary."""

    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks
        self.read_count = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.read_count += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize('status', [200, 302])
@pytest.mark.parametrize('announced_length', [False, True])
async def test_bounded_download_rejects_gzip_before_stream_or_decoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    announced_length: bool,
) -> None:
    """Neither final nor redirect bodies may expand before budget checks."""
    compressed = gzip.compress(b'x' * (4 * 1024 * 1024))
    stream = ObservedStream(compressed)
    target = tmp_path / 'archive.zip'
    target.write_bytes(b'previous archive')
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) > 1:
            return httpx.Response(200, content=b'ZIP')
        headers = {'content-encoding': 'gzip'}
        if announced_length:
            headers['content-length'] = str(len(compressed))
        if status == 302:
            headers['location'] = '/other.zip'
        return httpx.Response(status, headers=headers, stream=stream)

    install_mock_http_transport(monkeypatch, respond)

    with pytest.raises(SecurityError, match='identity Content-Encoding'):
        await RequestsAdapter().async_download_file(
            'https://example.test/archive.zip',
            str(target),
            max_bytes=8192,
            headers={'accept-encoding': 'gzip'},
        )

    assert stream.read_count == 0
    assert stream.closed is True
    assert len(seen) == 1
    assert seen[0].headers['accept-encoding'] == 'identity'
    assert target.read_bytes() == b'previous archive'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('size', [7, 8, 9])
@pytest.mark.parametrize('status', [200, 302])
async def test_stream_budget_covers_final_and_unannounced_redirect_bodies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    status: int,
) -> None:
    """Absent Content-Length cannot bypass limits while HTTPX follows URLs."""
    stream = ObservedStream(b'a' * 4, b'b' * (size - 4))
    target = tmp_path / 'archive.zip'
    target.write_bytes(b'previous archive')
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                status, headers={'location': '/final.zip'}, stream=stream
            )
        return httpx.Response(200, content=b'final')

    install_mock_http_transport(monkeypatch, respond)
    adapter = RequestsAdapter()
    if size > 8:
        with pytest.raises(SecurityError, match='download exceeds'):
            await adapter.async_download_file(
                'https://example.test/archive.zip', str(target), max_bytes=8
            )
        assert target.read_bytes() == b'previous archive'
        assert calls == 1
    else:
        await adapter.async_download_file(
            'https://example.test/archive.zip', str(target), max_bytes=8
        )
        assert target.read_bytes() == (
            b'final' if status == 302 else b'a' * 4 + b'b' * (size - 4)
        )
        assert calls == (2 if status == 302 else 1)
    assert stream.closed is True
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('announced_length', [False, True])
async def test_unbounded_download_keeps_http_content_decoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    announced_length: bool,
) -> None:
    """Existing callers without a byte budget retain decoded download bytes."""
    payload = b'ordinary response'
    compressed = gzip.compress(payload)
    stream = ObservedStream(compressed)
    headers = {'content-encoding': 'gzip'}
    if announced_length:
        headers['content-length'] = str(len(compressed))
    install_mock_http_transport(
        monkeypatch,
        lambda _request: httpx.Response(200, headers=headers, stream=stream),
    )
    target = tmp_path / 'response'

    await RequestsAdapter().async_download_file(
        'https://example.test/file', str(target)
    )

    assert target.read_bytes() == payload
    assert stream.closed is True


@pytest.mark.parametrize('status', [200, 302])
@pytest.mark.parametrize('follow_redirects', [False, True])
async def test_head_never_reads_encoded_bodies_or_rejects_metadata_length(
    monkeypatch: pytest.MonkeyPatch, status: int, follow_redirects: bool
) -> None:
    """HEAD metadata and redirects cannot trigger content decoding."""
    streams: list[ObservedStream] = []
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        stream = ObservedStream(gzip.compress(b'x' * (4 * 1024 * 1024)))
        streams.append(stream)
        return httpx.Response(
            status if len(requests) == 1 else 200,
            headers={
                'content-length': str(1 << 32),
                'content-encoding': 'gzip',
                'location': '/final',
            },
            stream=stream,
        )

    install_mock_http_transport(monkeypatch, respond)
    response = await RequestsAdapter(
        follow_redirects=follow_redirects
    ).async_head('https://example.test/start')

    redirected = status == 302 and follow_redirects
    assert len(requests) == (2 if redirected else 1)
    assert response.status_code == (200 if redirected else status)
    assert response.content == b''
    assert response.headers['content-length'] == str(1 << 32)
    assert response.headers['content-encoding'] == 'gzip'
    assert all(stream.read_count == 0 and stream.closed for stream in streams)
    assert all(
        request.headers['accept-encoding'] == 'identity'
        for request in requests
    )


@pytest.mark.parametrize('method', ['head', 'download'])
@pytest.mark.parametrize(
    ('initial', 'redirect', 'same_origin'),
    [
        ('https://origin.example.test/start', '/final', True),
        (
            'https://origin.example.test/start',
            'https://origin.example.test:443/final',
            True,
        ),
        (
            'https://origin.example.test/start',
            'https://cdn.example.test/final',
            False,
        ),
        (
            'https://origin.example.test/start',
            'https://origin.example.test:8443/final',
            False,
        ),
        (
            'http://origin.example.test/start',
            'https://origin.example.test/final',
            False,
        ),
    ],
)
async def test_redirect_credentials_are_confined_to_the_initial_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    initial: str,
    redirect: str,
    same_origin: bool,
) -> None:
    """All custom credentials are removed across scheme, host, or port."""
    seen: list[dict[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        if len(seen) == 1:
            return httpx.Response(
                302,
                headers={
                    'location': redirect,
                    'set-cookie': 'session=synthetic; Domain=example.test',
                },
            )
        return httpx.Response(200, content=b'ZIP')

    install_mock_http_transport(monkeypatch, respond)
    adapter = RequestsAdapter(
        default_headers={
            'X-API-Key': 'synthetic-default',
            'Authorization': 'Bearer synthetic-auth',
            'User-Agent': 'test-client',
        }
    )
    headers = {
        'X-Custom-Credential': 'synthetic-request',
        'Cookie': 'initial=synthetic',
        'Accept': 'application/zip',
    }
    if method == 'head':
        response = await adapter.async_head(initial, headers=headers)
        assert response.status_code == 200
    else:
        target = tmp_path / 'archive.zip'
        await adapter.async_download_file(
            initial, str(target), headers=headers, max_bytes=8
        )
        assert target.read_bytes() == b'ZIP'

    assert len(seen) == 2
    assert seen[0]['x-api-key'] == 'synthetic-default'
    assert seen[0]['x-custom-credential'] == 'synthetic-request'
    assert seen[1]['user-agent'] == 'test-client'
    assert seen[1]['accept'] == 'application/zip'
    if same_origin:
        assert seen[1]['x-api-key'] == 'synthetic-default'
        assert seen[1]['x-custom-credential'] == 'synthetic-request'
        assert seen[1]['authorization'] == 'Bearer synthetic-auth'
        assert 'session=synthetic' in seen[1]['cookie']
    else:
        assert 'x-api-key' not in seen[1]
        assert 'x-custom-credential' not in seen[1]
        assert 'authorization' not in seen[1]
        assert 'cookie' not in seen[1]


INITIAL = 'https://origin.example.test/start'


def _redirect_once(
    location: str, seen: list[httpx.URL]
) -> Callable[[httpx.Request], httpx.Response]:
    """Redirect the first request and serve a body to any later hop."""

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if len(seen) == 1:
            return httpx.Response(302, headers={'location': location})
        return httpx.Response(200, content=b'ZIP')

    return respond


async def _request(
    adapter: RequestsAdapter, method: str, target: Path
) -> None:
    """Send one HEAD or bounded download through the shared adapter."""
    if method == 'head':
        await adapter.async_head(INITIAL)
    else:
        await adapter.async_download_file(INITIAL, str(target), max_bytes=8)


@pytest.mark.parametrize('method', ['head', 'download'])
@pytest.mark.parametrize('allow_cross_origin', [True, False])
@pytest.mark.parametrize(
    'location',
    ['http://origin.example.test/final', 'http://mirror.example.test/final'],
)
async def test_https_request_is_never_redirected_to_another_scheme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    allow_cross_origin: bool,
    location: str,
) -> None:
    """The plaintext hop is rejected before it is sent, on any host."""
    seen: list[httpx.URL] = []
    install_mock_http_transport(monkeypatch, _redirect_once(location, seen))
    target = tmp_path / 'archive.zip'
    target.write_bytes(b'previous archive')
    adapter = RequestsAdapter(allow_cross_origin_redirects=allow_cross_origin)

    with pytest.raises(SecurityError, match='leaves HTTPS'):
        await _request(adapter, method, target)

    assert seen == [httpx.URL(INITIAL)]
    assert target.read_bytes() == b'previous archive'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('method', ['head', 'download'])
@pytest.mark.parametrize(
    'location',
    [
        'https://cdn.example.test/final',
        'https://origin.example.test:8443/final',
    ],
)
async def test_origin_bound_adapter_rejects_cross_origin_https_hops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    location: str,
) -> None:
    """A changed host or port is rejected before the request is sent."""
    seen: list[httpx.URL] = []
    install_mock_http_transport(monkeypatch, _redirect_once(location, seen))
    target = tmp_path / 'archive.zip'
    target.write_bytes(b'previous archive')
    adapter = RequestsAdapter(allow_cross_origin_redirects=False)

    with pytest.raises(
        SecurityError,
        match=re.escape(
            'outside the requested origin https://origin.example.test'
        ),
    ):
        await _request(adapter, method, target)

    assert seen == [httpx.URL(INITIAL)]
    assert target.read_bytes() == b'previous archive'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('method', ['head', 'download'])
@pytest.mark.parametrize(
    'location', ['/final', 'https://origin.example.test:443/final']
)
async def test_origin_bound_adapter_follows_same_origin_redirects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    location: str,
) -> None:
    """Redirects that keep scheme, host, and port remain supported."""
    seen: list[httpx.URL] = []
    install_mock_http_transport(monkeypatch, _redirect_once(location, seen))
    target = tmp_path / 'archive.zip'
    adapter = RequestsAdapter(allow_cross_origin_redirects=False)

    await _request(adapter, method, target)

    assert [(url.scheme, url.host, url.port, url.path) for url in seen] == [
        ('https', 'origin.example.test', None, '/start'),
        ('https', 'origin.example.test', None, '/final'),
    ]
    if method == 'download':
        assert target.read_bytes() == b'ZIP'


async def test_rejected_redirect_diagnostic_omits_credentials_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the target origin is reported, never its user info or query."""
    location = (
        'http://user:synthetic-secret@'  # pragma: allowlist secret
        'mirror.example.test/a?code=x1'
    )
    install_mock_http_transport(monkeypatch, _redirect_once(location, []))

    with pytest.raises(SecurityError) as raised:
        await _request(RequestsAdapter(), 'download', tmp_path / 'a.zip')

    assert str(raised.value) == (
        'Security violation: redirect target http://mirror.example.test '
        'leaves HTTPS'
    )
    assert list(tmp_path.iterdir()) == []
