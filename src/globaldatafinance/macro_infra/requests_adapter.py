"""Adapt asynchronous HTTP requests and streamed filesystem writes."""

import contextlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from ..macro_exceptions import (
    DiskFullError,
    FileWriteError,
    PathPermissionError,
    SecurityError,
)
from .temporary_files import reserve_temporary_path


class RequestsAdapter:
    """Adapt httpx for asynchronous HTTP requests and streamed downloads.

    Provides asynchronous HTTP HEAD requests and streamed file downloads.
    """

    def __init__(
        self,
        timeout: float = 60.0,
        max_redirects: int = 5,
        verify: bool = True,
        http2: bool = False,
        default_headers: Mapping[str, str] | None = None,
        follow_redirects: bool = True,
    ):
        """Initialize the httpx adapter.

        Args:
            timeout: Default request timeout in seconds
            max_redirects: Maximum number of redirects to follow. Default
                lowered to 5 (from a previous 20) as a hardening measure:
                legitimate CVM/B3 endpoints never chain more than 1-2
                redirects, and a low cap shortens the blast radius of
                redirect-loop attacks. Override for custom transports.
            verify: Verify SSL certificates
            http2: Enable HTTP/2
            default_headers: Optional headers merged into every request.
                Headers explicitly supplied to a request take precedence.
            follow_redirects: Whether requests may follow HTTP redirects.
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.verify = verify
        self.http2 = http2
        self.follow_redirects = follow_redirects
        self.default_headers = (
            dict(default_headers) if default_headers is not None else None
        )

    def _merge_headers(
        self, headers: dict[str, str] | None
    ) -> dict[str, str] | None:
        """Merge request headers over the adapter's default headers."""
        if self.default_headers is None:
            return headers

        merged_headers = dict(self.default_headers)
        if headers is None:
            return merged_headers

        for key, value in headers.items():
            normalized_key = key.casefold()
            for existing_key in tuple(merged_headers):
                if existing_key.casefold() == normalized_key:
                    del merged_headers[existing_key]
            merged_headers[key] = value

        return merged_headers

    async def async_head(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a HEAD request to inspect headers without downloading a body.

        Useful for checking Content-Length, Content-Type, etc. before download.

        Args:
            url: Request URL
            headers: Custom headers
            timeout: Specific timeout for this request
            **kwargs: Additional httpx arguments

        Returns:
            httpx.Response: Request response (no body, only headers)
        """
        request_headers = self._merge_headers(headers)
        async with httpx.AsyncClient(
            timeout=timeout or self.timeout,
            follow_redirects=self.follow_redirects,
            max_redirects=self.max_redirects,
            verify=self.verify,
            http2=self.http2,
        ) as client:
            return await client.head(url, headers=request_headers, **kwargs)

    async def async_download_file(
        self,
        url: str,
        output_path: str,
        chunk_size: int = 8192,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> None:
        """Download a file asynchronously with streaming.

        Args:
            url: File URL
            output_path: Path to save the file
            chunk_size: Chunk size for streaming
            headers: Custom headers
            timeout: Specific timeout for this request
            max_bytes: Optional maximum number of response bytes to persist.

        Raises:
            httpx.HTTPStatusError: If HTTP status indicates error
            httpx.RequestError: If network error occurs
            OSError: If disk write fails
        """
        staging_path = await self.async_download_to_staging_file(
            url=url,
            output_path=output_path,
            chunk_size=chunk_size,
            headers=headers,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        target_path = Path(output_path)

        try:
            staging_path.replace(target_path)
        except BaseException:
            _remove_staging_file(staging_path)
            raise

    async def async_download_to_staging_file(
        self,
        url: str,
        output_path: str,
        chunk_size: int = 8192,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> Path:
        """Stream a response into a unique file beside the final target.

        The returned path is owned by the caller after a successful transfer.
        Before that handoff, every failure, including cancellation, removes
        only the staging file created by this call.
        """
        _validate_download_limit(max_bytes)
        target_path = Path(output_path)
        request_headers = self._merge_headers(headers)
        staging_path: Path | None = None

        try:
            staging_path = reserve_temporary_path(target_path, suffix='.part')

            async with (
                httpx.AsyncClient(
                    timeout=timeout or self.timeout,
                    follow_redirects=self.follow_redirects,
                    max_redirects=self.max_redirects,
                    verify=self.verify,
                    http2=self.http2,
                ) as client,
                client.stream('GET', url, headers=request_headers) as response,
            ):
                response.raise_for_status()
                _validate_content_length(
                    response.headers.get('content-length'),
                    max_bytes,
                    output_path,
                )

                with staging_path.open('wb') as file_handle:
                    written_bytes = 0
                    async for chunk in response.aiter_bytes(
                        chunk_size=chunk_size
                    ):
                        if chunk:
                            written_bytes += len(chunk)
                            if (
                                max_bytes is not None
                                and written_bytes > max_bytes
                            ):
                                raise SecurityError(
                                    'download exceeds configured byte limit '
                                    f'({written_bytes} > {max_bytes})',
                                    output_path,
                                )
                            try:
                                file_handle.write(chunk)
                            except OSError as write_err:
                                # Critical: disk full, permission error, etc
                                err_msg = str(write_err).lower()
                                if (
                                    'enospc' in err_msg
                                    or 'no space left' in err_msg
                                    or 'disk full' in err_msg
                                ):
                                    raise DiskFullError(
                                        output_path
                                    ) from write_err
                                if (
                                    'permission denied' in err_msg
                                    or 'eacces' in err_msg
                                ):
                                    raise PathPermissionError(
                                        output_path
                                    ) from write_err
                                raise FileWriteError(
                                    output_path, str(write_err)
                                ) from write_err

            return staging_path

        except BaseException:
            if staging_path is not None:
                _remove_staging_file(staging_path)

            raise


def _remove_staging_file(staging_path: Path) -> None:
    """Remove one staging path without affecting its final target."""
    with contextlib.suppress(OSError):
        staging_path.unlink(missing_ok=True)


def _validate_download_limit(max_bytes: int | None) -> None:
    """Reject invalid byte limits before any network or filesystem work."""
    if max_bytes is not None and max_bytes < 1:
        raise ValueError('max_bytes must be at least one when provided')


def _validate_content_length(
    raw_content_length: object,
    max_bytes: int | None,
    output_path: str,
) -> None:
    """Reject an announced response body that exceeds the caller's budget."""
    if raw_content_length is None or max_bytes is None:
        return
    if not isinstance(raw_content_length, str):
        return
    try:
        content_length = int(raw_content_length)
    except (TypeError, ValueError):
        return
    if content_length > max_bytes:
        raise SecurityError(
            'download Content-Length exceeds configured byte limit '
            f'({content_length} > {max_bytes})',
            output_path,
        )
