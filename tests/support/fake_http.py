"""Small deterministic HTTP client fakes for streamed-download tests."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

import httpx
import pytest


def install_mock_http_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Run real HTTPX streaming and redirect logic with a local transport."""
    factory = partial(
        httpx.AsyncClient, transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(httpx, 'AsyncClient', factory)


class FakeResponse:
    """Minimal streamed response with real HTTP status semantics."""

    def __init__(
        self,
        url: str,
        chunks: list[bytes],
        *,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self.headers = headers or {}
        self._chunks = chunks
        self._status_response = httpx.Response(
            status_code,
            request=httpx.Request('GET', url),
        )
        self.iterated = False

    def raise_for_status(self) -> None:
        """Raise the same status exception as an httpx response."""
        self._status_response.raise_for_status()

    async def aiter_bytes(self, *, chunk_size: int):
        """Yield configured chunks while accepting httpx's chunk argument."""
        del chunk_size
        self.iterated = True
        for chunk in self._chunks:
            yield chunk


class _FakeStream:
    def __init__(self, response: FakeResponse):
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


def install_fake_http_client(
    monkeypatch: pytest.MonkeyPatch,
    response_factory: Callable[[str], FakeResponse],
    *,
    head_response_factory: Callable[[str], FakeResponse] | None = None,
) -> None:
    """Install a fake AsyncClient backed by caller-owned response factories."""
    head_factory = head_response_factory or response_factory

    class FakeAsyncClient:
        def __init__(self, *_args: object, **_kwargs: object):
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(
            self, method: str, url: str, **_kwargs: object
        ) -> _FakeStream:
            assert method == 'GET'
            return _FakeStream(response_factory(url))

        async def head(self, url: str, **_kwargs: object) -> FakeResponse:
            return head_factory(url)

    monkeypatch.setattr(httpx, 'AsyncClient', FakeAsyncClient)
