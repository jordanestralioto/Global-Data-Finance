"""CVM downloads follow redirects only within the requested HTTPS origin."""

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from globaldatafinance.brazil.cvm.ingestion.http import CvmDownloadAdapter
from tests.support.fake_http import install_mock_http_transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SOURCE = (
    'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
    'dfp_cia_aberta_2024.zip'
)


def _archive_bytes() -> bytes:
    """Create a complete regulatory ZIP without any external source."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('data.csv', b'id;value\n1;valid\n')
    return buffer.getvalue()


@pytest.mark.parametrize(
    ('location', 'cause'),
    [
        ('http://dados.cvm.gov.br/dfp.zip', 'leaves HTTPS'),
        ('http://mirror.example.test/dfp.zip', 'leaves HTTPS'),
        ('https://mirror.example.test/dfp.zip', 'outside the requested'),
        ('https://dados.cvm.gov.br:8443/dfp.zip', 'outside the requested'),
        ('http://temporarily.example.test/dfp.zip', 'leaves HTTPS'),
        ('https://timeout.example.test/dfp.zip', 'outside the requested'),
        ('https://unavailable.example.test/dfp.zip', 'outside the requested'),
    ],
)
async def test_redirect_outside_the_cvm_origin_fails_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
    cause: str,
) -> None:
    """The unsafe hop is never sent and the caller's ZIP is preserved."""
    payload = _archive_bytes()
    target = tmp_path / 'dfp_cia_aberta_2024.zip'
    target.write_bytes(b'previous caller-owned ZIP')
    seen: list[httpx.URL] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url == httpx.URL(SOURCE):
            return httpx.Response(302, headers={'location': location})
        return httpx.Response(200, content=payload)

    install_mock_http_transport(monkeypatch, respond)
    adapter = CvmDownloadAdapter(None, max_retries=2, initial_backoff=0)
    result = await adapter.async_download_docs(
        [(SOURCE, 'DFP', '2024', str(tmp_path))]
    )

    assert result.successful_downloads == []
    assert result.failed_downloads['DFP_2024'].startswith('SecurityError: ')
    assert cause in result.failed_downloads['DFP_2024']
    assert seen == [httpx.URL(SOURCE)]
    assert target.read_bytes() == b'previous caller-owned ZIP'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize(
    'location',
    [
        '/dados/CIA_ABERTA/DOC/DFP/DADOS/current.zip',
        'https://dados.cvm.gov.br:443/current.zip',
    ],
)
async def test_redirect_within_the_cvm_origin_still_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    """A same-origin HTTPS redirect keeps the existing download behavior."""
    payload = _archive_bytes()
    seen: list[httpx.URL] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if len(seen) == 1:
            return httpx.Response(302, headers={'location': location})
        return httpx.Response(200, content=payload)

    install_mock_http_transport(monkeypatch, respond)
    result = await CvmDownloadAdapter(None).async_download_docs(
        [(SOURCE, 'DFP', '2024', str(tmp_path))]
    )

    assert result.successful_downloads == ['DFP_2024']
    assert result.failed_downloads == {}
    assert [(url.scheme, url.host, url.port) for url in seen] == [
        ('https', 'dados.cvm.gov.br', None),
        ('https', 'dados.cvm.gov.br', None),
    ]
    assert (tmp_path / 'dfp_cia_aberta_2024.zip').read_bytes() == payload
