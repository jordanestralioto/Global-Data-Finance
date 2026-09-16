"""Regression tests for atomic CVM download promotion."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
)
from globaldatafinance.core.config import ArchiveSafetySettings
from tests.support.fake_http import FakeResponse, install_fake_http_client

pytestmark = pytest.mark.unit


def _zip_test_data() -> bytes:
    """Build a small structurally valid CVM-like ZIP payload."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('data.csv', 'id;value\n1;valid\n')
    return buffer.getvalue()


def _staging_files(target_path: Path) -> list[Path]:
    """Return hidden download staging files beside one final target."""
    return sorted(target_path.parent.glob(f'.{target_path.name}.*.part'))


@pytest.mark.asyncio
class TestCvmStagedDownloadFlow:
    async def test_invalid_zip_preserves_existing_target_and_result_error(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'previous valid archive'
        target.write_bytes(old_bytes)
        invalid_bytes = b'not a ZIP archive'

        def response_factory(url: str) -> FakeResponse:
            return FakeResponse(
                url,
                [invalid_bytes],
                headers={'content-length': str(len(invalid_bytes))},
            )

        install_fake_http_client(monkeypatch, response_factory)
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=MagicMock(), max_retries=0
        )

        result = await adapter.async_download_docs(
            [
                (
                    'https://example.com/file.zip',
                    'DRE',
                    '2023',
                    str(tmp_path),
                )
            ],
            automatic_extractor=False,
        )

        assert result.successful_downloads == []
        assert result.failed_downloads == {
            'DRE_2023': (
                'Downloaded file corrupted, incomplete, or invalid ZIP'
            )
        }
        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    async def test_valid_zip_promotes_after_validation_without_extraction(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'previous archive'
        target.write_bytes(old_bytes)
        payload = _zip_test_data()

        def response_factory(url: str) -> FakeResponse:
            return FakeResponse(
                url,
                [payload[:13], payload[13:]],
                headers={'content-length': str(len(payload))},
            )

        install_fake_http_client(monkeypatch, response_factory)
        extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=extractor, max_retries=0
        )

        result = await adapter.async_download_docs(
            [
                (
                    'https://example.com/file.zip',
                    'DRE',
                    '2023',
                    str(tmp_path),
                )
            ],
            automatic_extractor=False,
        )

        assert result.successful_downloads == ['DRE_2023']
        assert result.failed_downloads == {}
        assert target.read_bytes() == payload
        assert _staging_files(target) == []
        extractor.extract.assert_not_called()

    async def test_limit_rejection_preserves_existing_target(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'previous archive'
        target.write_bytes(old_bytes)
        limit = ArchiveSafetySettings().max_archive_bytes
        response = FakeResponse(
            'https://example.com/file.zip',
            [b'oversized response'],
            headers={'content-length': str(limit + 1)},
        )
        install_fake_http_client(monkeypatch, lambda _url: response)
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=MagicMock(), max_retries=5
        )

        result = await adapter.async_download_docs(
            [
                (
                    'https://example.com/file.zip',
                    'DRE',
                    '2023',
                    str(tmp_path),
                )
            ],
            automatic_extractor=False,
        )

        assert result.successful_downloads == []
        assert 'SecurityError' in result.failed_downloads['DRE_2023']
        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []

    async def test_exhausted_retries_preserve_existing_target(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / 'file.zip'
        old_bytes = b'previous archive'
        target.write_bytes(old_bytes)
        calls = 0

        def response_factory(url: str) -> FakeResponse:
            nonlocal calls
            calls += 1
            return FakeResponse(url, [], status_code=503)

        install_fake_http_client(monkeypatch, response_factory)
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=MagicMock(),
            max_retries=2,
            initial_backoff=0.0,
            max_backoff=0.0,
        )

        result = await adapter.async_download_docs(
            [
                (
                    'https://example.com/file.zip',
                    'DRE',
                    '2023',
                    str(tmp_path),
                )
            ],
            automatic_extractor=False,
        )

        assert calls == 3
        assert result.successful_downloads == []
        assert 'NetworkError' in result.failed_downloads['DRE_2023']
        assert target.read_bytes() == old_bytes
        assert _staging_files(target) == []
