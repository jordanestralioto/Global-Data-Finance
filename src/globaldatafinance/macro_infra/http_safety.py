"""Constrain redirect headers and bounded HTTP response bodies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import cast

import httpx

from ..macro_exceptions import SecurityError

_PUBLIC_REDIRECT_HEADERS = frozenset(
    {
        'accept',
        'accept-encoding',
        'accept-language',
        'connection',
        'host',
        'user-agent',
    }
)


def redirect_header_hook(
    url: str,
) -> Callable[[httpx.Request], Awaitable[None]]:
    """Keep credentials on the original scheme, host, and port only."""
    original = httpx.URL(url)
    origin = (original.scheme, original.host, original.port)

    async def restrict_headers(request: httpx.Request) -> None:
        target = request.url
        if (target.scheme, target.host, target.port) != origin:
            for name in tuple(request.headers):
                if name not in _PUBLIC_REDIRECT_HEADERS:
                    del request.headers[name]

    return restrict_headers


def bounded_download_headers(
    headers: Mapping[str, str] | None, max_bytes: int | None
) -> dict[str, str] | None:
    """Disable HTTP content decoding when the caller sets a byte budget."""
    if max_bytes is None:
        return dict(headers) if headers is not None else None
    return identity_headers(headers)


def identity_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Request unencoded content while retaining other caller headers."""
    merged = httpx.Headers(headers)
    merged['Accept-Encoding'] = 'identity'
    return dict(merged.items())


async def discard_head_body(response: httpx.Response) -> None:
    """Close HEAD bodies without reading or decoding, preserving metadata."""
    await cast(httpx.AsyncByteStream, response.stream).aclose()
    response.stream = httpx.ByteStream(b'')


def validate_download_response_headers(
    headers: Mapping[str, str], max_bytes: int | None, output_path: str
) -> None:
    """Reject encoded or oversized bounded responses before body reading."""
    if max_bytes is None:
        return
    encoding = headers.get('content-encoding', '').strip().casefold()
    if encoding not in {'', 'identity'}:
        raise SecurityError(
            'bounded download requires identity Content-Encoding', output_path
        )
    raw_length = headers.get('content-length')
    try:
        length = int(raw_length) if raw_length is not None else None
    except (TypeError, ValueError):
        return
    if length is not None and length > max_bytes:
        raise SecurityError(
            'download Content-Length exceeds configured byte limit '
            f'({length} > {max_bytes})',
            output_path,
        )


def download_response_hook(
    max_bytes: int | None, output_path: str
) -> Callable[[httpx.Response], Awaitable[None]]:
    """Enforce the budget before HTTPX consumes redirect or final bodies."""

    async def guard_response(response: httpx.Response) -> None:
        validate_download_response_headers(
            response.headers, max_bytes, output_path
        )
        if max_bytes is not None:
            response.stream = _BoundedResponseStream(
                cast(httpx.AsyncByteStream, response.stream),
                max_bytes,
                output_path,
            )

    return guard_response


class _BoundedResponseStream(httpx.AsyncByteStream):
    """Count transport bytes before any HTTPX buffering or content decoding."""

    def __init__(
        self, stream: httpx.AsyncByteStream, limit: int, output_path: str
    ) -> None:
        self._stream = stream
        self._limit = limit
        self._output_path = output_path

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self._stream:
            received += len(chunk)
            if received > self._limit:
                raise SecurityError(
                    'download exceeds configured byte limit '
                    f'({received} > {self._limit})',
                    self._output_path,
                )
            yield chunk

    async def aclose(self) -> None:
        """Release the underlying response even when its body is rejected."""
        await self._stream.aclose()
