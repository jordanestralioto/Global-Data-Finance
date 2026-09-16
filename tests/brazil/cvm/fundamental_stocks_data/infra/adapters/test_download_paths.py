"""Regression coverage for CVM URL-derived download targets."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    DownloadResultCVM,
)
from globaldatafinance.macro_exceptions import SecurityError

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'url',
    [
        'https://example.test/CON.zip',
        'https://example.test/aux.txt',
        'https://example.test/COM1.csv',
        'https://example.test/report%3F.csv',
        'https://example.test/report%3C.csv',
        'https://example.test/report%7C.csv',
        'https://example.test/report%2E',
        'https://example.test/report%20',
        'https://example.test/COM%C2%B9.csv',
        'https://example.test/COM%C2%B2.csv',
        'https://example.test/COM%C2%B3.csv',
        'https://example.test/LPT%C2%B9.csv',
        'https://example.test/LPT%C2%B2.csv',
        'https://example.test/LPT%C2%B3.csv',
        'https://example.test/CONIN%24.csv',
        'https://example.test/CONOUT%24.csv',
    ],
)
async def test_invalid_url_basename_fails_before_download_or_promotion(
    tmp_path, url
):
    """Win32-invalid URL names fail before any staging or promotion."""
    output_dir = tmp_path / 'output'
    adapter = AsyncDownloadAdapterCVM(file_extractor_repository=MagicMock())
    adapter._download_with_retry = AsyncMock()

    with pytest.raises(SecurityError):
        await adapter._download_and_extract(
            url,
            str(output_dir),
            'DRE',
            '2023',
            DownloadResultCVM(),
            MagicMock(),
        )

    adapter._download_with_retry.assert_not_awaited()
    assert not output_dir.exists()
