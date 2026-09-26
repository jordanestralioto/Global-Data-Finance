"""Local HTTP fixtures and phase instrumentation for the CVM benchmark."""

from __future__ import annotations

import io
import threading
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import httpx

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    ParquetExtractorAdapterCVM,
)

MEBIBYTE = 1024**2
DEFAULT_CHUNKS = (8 * 1024, 64 * 1024, 256 * 1024)
DEFAULT_BATCH_SIZE = 3
DEFAULT_PAYLOAD_MIB = 4
DEFAULT_ROWS = 256
MAX_PAYLOAD_MIB = 64
SERVER_CHUNK_SIZE = 64 * 1024
PHASES = ('get', 'head', 'validation', 'extraction')


class PhaseMeasurements:
    """Collect stage timings and byte counts from one measured batch."""

    def __init__(self) -> None:
        """Initialize empty measurement totals for each phase."""
        self._lock = threading.Lock()
        self._phases: dict[str, dict[str, float | int]] = {
            phase: {
                'seconds': 0.0,
                'operations': 0,
                'transferred_bytes': 0,
                'processed_bytes': 0,
                'announced_bytes': 0,
            }
            for phase in PHASES
        }
        self.client_initializations = 0
        self.client_initialization_seconds = 0.0

    def add_phase(
        self,
        phase: str,
        seconds: float,
        *,
        transferred_bytes: int = 0,
        processed_bytes: int = 0,
        announced_bytes: int = 0,
    ) -> None:
        """Accumulate one completed phase measurement."""
        with self._lock:
            record = self._phases[phase]
            record['seconds'] = float(record['seconds']) + seconds
            record['operations'] = int(record['operations']) + 1
            record['transferred_bytes'] = (
                int(record['transferred_bytes']) + transferred_bytes
            )
            record['processed_bytes'] = (
                int(record['processed_bytes']) + processed_bytes
            )
            record['announced_bytes'] = (
                int(record['announced_bytes']) + announced_bytes
            )

    def add_client_initialization(self, seconds: float) -> None:
        """Record one HTTPX client construction."""
        with self._lock:
            self.client_initializations += 1
            self.client_initialization_seconds += seconds

    def snapshot(self) -> dict[str, Any]:
        """Return a detached view of accumulated timings and byte counts."""
        with self._lock:
            phases = {
                phase: dict(values) for phase, values in self._phases.items()
            }
            client_initializations = self.client_initializations
            client_initialization_seconds = self.client_initialization_seconds
        return {
            'phases': phases,
            'client_initializations': client_initializations,
            'client_initialization_seconds': client_initialization_seconds,
        }


class TimedParquetExtractor:
    """Measure one production extraction call without changing its behavior."""

    def __init__(
        self,
        delegate: ParquetExtractorAdapterCVM,
        measurements: PhaseMeasurements,
    ) -> None:
        """Store the production extractor and its phase measurements."""
        self._delegate = delegate
        self._measurements = measurements

    def extract(self, source_path: str, destination_path: str) -> None:
        """Measure one extraction call and delegate to production code."""
        started = time.perf_counter()
        processed_bytes = 0
        try:
            with zipfile.ZipFile(source_path, 'r') as archive:
                processed_bytes = sum(
                    member.file_size
                    for member in archive.infolist()
                    if not member.is_dir()
                    and member.filename.lower().endswith('.csv')
                )
            self._delegate.extract(source_path, destination_path)
        finally:
            self._measurements.add_phase(
                'extraction',
                time.perf_counter() - started,
                processed_bytes=processed_bytes,
            )


class MeasuredDownloadAdapter(AsyncDownloadAdapterCVM):
    """Measure HTTP and archive-validation phases around production methods."""

    def __init__(
        self,
        extractor: TimedParquetExtractor,
        measurements: PhaseMeasurements,
        *,
        chunk_size: int,
        max_concurrent: int,
    ) -> None:
        """Configure production download methods with measurement hooks."""
        self._measurements = measurements
        super().__init__(
            file_extractor_repository=extractor,
            max_concurrent=max_concurrent,
            chunk_size=chunk_size,
            timeout=30.0,
            max_retries=0,
            http2=False,
            automatic_extractor=True,
        )

    async def _stream_download(self, url: str, filepath: str) -> Path:
        started = time.perf_counter()
        staging_path: Path | None = None
        try:
            staging_path = await super()._stream_download(url, filepath)
            return staging_path
        finally:
            transferred_bytes = (
                staging_path.stat().st_size
                if staging_path is not None and staging_path.exists()
                else 0
            )
            self._measurements.add_phase(
                'get',
                time.perf_counter() - started,
                transferred_bytes=transferred_bytes,
            )

    async def _get_content_length(self, url: str) -> int | None:
        started = time.perf_counter()
        announced_bytes = 0
        try:
            content_length = await super()._get_content_length(url)
            announced_bytes = content_length or 0
            return content_length
        finally:
            self._measurements.add_phase(
                'head',
                time.perf_counter() - started,
                announced_bytes=announced_bytes,
            )

    def _validate_downloaded_file(
        self,
        filepath: str,
        expected_size: int | None = None,
    ) -> bool:
        started = time.perf_counter()
        archive_bytes = (
            Path(filepath).stat().st_size if Path(filepath).is_file() else 0
        )
        try:
            return super()._validate_downloaded_file(
                filepath,
                expected_size,
            )
        finally:
            self._measurements.add_phase(
                'validation',
                time.perf_counter() - started,
                processed_bytes=archive_bytes,
            )


class _PayloadHttpServer(ThreadingHTTPServer):
    """HTTP/1.1 fixture server for a fixed ZIP response body."""

    payload: bytes
    allow_reuse_address = True
    daemon_threads = True


class _PayloadRequestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_HEAD(self) -> None:
        """Return the size of the deterministic local archive."""
        server = cast(_PayloadHttpServer, self.server)
        self.send_response(200)
        self.send_header('Content-Length', str(len(server.payload)))
        self.send_header('Content-Type', 'application/zip')
        self.end_headers()

    def do_GET(self) -> None:
        """Stream the deterministic local archive in fixed server chunks."""
        server = cast(_PayloadHttpServer, self.server)
        self.send_response(200)
        self.send_header('Content-Length', str(len(server.payload)))
        self.send_header('Content-Type', 'application/zip')
        self.end_headers()
        for offset in range(0, len(server.payload), SERVER_CHUNK_SIZE):
            self.wfile.write(
                server.payload[offset : offset + SERVER_CHUNK_SIZE]
            )

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep request logging out of benchmark output."""


@contextmanager
def serve_payload(payload: bytes) -> Iterator[str]:
    """Serve one fixed archive on an ephemeral loopback port."""
    server = _PayloadHttpServer(
        ('127.0.0.1', 0),
        _PayloadRequestHandler,
    )
    server.payload = payload
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        server_address = server.server_address
        address = server_address[0]
        host = (
            address.decode('ascii')
            if isinstance(address, bytes)
            else str(address)
        )
        port = int(server_address[1])
        yield f'http://{host}:{port}/dfp_cia_aberta_2024.zip'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def build_fixture(payload_mib: int) -> tuple[bytes, bytes, int]:
    """Create one deterministic stored ZIP and its logical CSV row count."""
    payload = bytes(payload_mib * MEBIBYTE)
    rows = DEFAULT_ROWS
    csv_bytes = (
        'id;amount\n'
        + ''.join(f'{index};{index / 100:.2f}\n' for index in range(rows))
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, 'w', compression=zipfile.ZIP_STORED
    ) as archive:
        for member_name, member_bytes in (
            ('payload.bin', payload),
            ('filings.csv', csv_bytes),
        ):
            member = zipfile.ZipInfo(
                member_name,
                date_time=(2020, 1, 1, 0, 0, 0),
            )
            member.compress_type = zipfile.ZIP_STORED
            archive.writestr(member, member_bytes)
    return buffer.getvalue(), csv_bytes, rows


@contextmanager
def track_httpx_client_construction(
    measurements: PhaseMeasurements,
) -> Iterator[None]:
    """Measure the synchronous constructor cost of each HTTPX client."""
    client_type: Any = httpx.AsyncClient

    class _MeasuredAsyncClient(client_type):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            started = time.perf_counter()
            try:
                super().__init__(*args, **kwargs)
            finally:
                measurements.add_client_initialization(
                    time.perf_counter() - started
                )

    with patch(
        'globaldatafinance.macro_infra.requests_adapter.httpx.AsyncClient',
        _MeasuredAsyncClient,
    ):
        yield
