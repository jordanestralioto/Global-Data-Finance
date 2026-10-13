"""Optional HTTP archive metadata does not bypass ZIP validation."""

from unittest.mock import AsyncMock

import httpx
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    AsyncDownloadAdapterCVM,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('value', 'expected'), [(None, None), ('100', 100), ('invalid', None)]
)
async def test_content_length_is_validated_as_optional_metadata(
    value: str | None,
    expected: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Present sizes are parsed; unavailable metadata remains optional."""
    adapter = AsyncDownloadAdapterCVM(None)
    monkeypatch.setattr(
        adapter.requests_adapter,
        'async_head',
        AsyncMock(
            return_value=httpx.Response(
                200,
                headers={'content-length': value} if value is not None else {},
            )
        ),
    )
    assert (
        await adapter._get_content_length('https://example.com/file.zip')
        == expected
    )
