"""Official CVM catalog inventory behind a deterministic HTTP boundary."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from scripts import cvm_catalog
from scripts import real_validation as cli
from scripts.real_validation_matrix import build_cases

pytestmark = pytest.mark.unit


def _client(
    monkeypatch: pytest.MonkeyPatch, payload: bytes, status: int = 200
):
    """Replace only the HTTP transport used to fetch an official listing."""
    original = httpx.Client
    requests: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=payload)

    def factory(**kwargs):
        return original(transport=httpx.MockTransport(response), **kwargs)

    monkeypatch.setattr(cvm_catalog.httpx, 'Client', factory)
    return requests


def _cases(tmp_path: Path):
    """Select the historical IPE boundary omitted by the previous matrix."""
    return build_cases(
        source='cvm',
        initial_year=2003,
        last_year=2004,
        document='IPE',
        cotahist_path=None,
        cvm_output=str(tmp_path),
    )


def test_catalog_records_all_published_selected_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The matrix is checked against exact official relative archive links."""
    requests = _client(
        monkeypatch,
        b'<a href="../">up</a><a href="ipe_cia_aberta_2003.zip">2003</a>'
        b'<a href="ipe_cia_aberta_2004.zip">2004</a>',
    )
    result = cvm_catalog.verify_catalog(_cases(tmp_path), 5)

    assert result['status'] == 'passed'
    assert result['publishedArchiveCount'] == 2
    assert result['selectedArchiveCount'] == 2
    assert result['allPublishedArchivesSelected'] is True
    assert result['documents'][0]['publishedYears'] == [2003, 2004]
    assert str(requests[0].url) == (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/'
    )


def test_catalog_reports_published_archives_outside_selected_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An incomplete matrix is visible instead of claiming full coverage."""
    _client(monkeypatch, b'<a href="ipe_cia_aberta_2002.zip">older</a>')
    result = cvm_catalog.verify_catalog(_cases(tmp_path), 5)
    assert result['status'] == 'failed'
    assert result['allPublishedArchivesSelected'] is False
    assert result['documents'][0]['publishedYearsNotSelected'] == [2002]
    assert result['documents'][0]['selectedYearsNotListed'] == [2003, 2004]


def test_catalog_omissions_stop_cli_before_running_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A full-catalog claim cannot succeed with a partial source matrix."""
    import json

    _client(
        monkeypatch,
        b'<a href="ipe_cia_aberta_2003.zip">2003</a>'
        b'<a href="ipe_cia_aberta_2004.zip">2004</a>',
    )

    def unexpected_campaign(*_args, **_kwargs):
        pytest.fail('An incomplete catalog must stop before case execution')

    monkeypatch.setattr(cli, 'run_campaign', unexpected_campaign)
    report = tmp_path / 'report'
    result = cli.main(
        [
            '--source',
            'cvm',
            '--document',
            'IPE',
            '--initial-year',
            '2003',
            '--last-year',
            '2003',
            '--verify-cvm-catalog',
            '--report',
            str(report),
            '--cvm-output',
            str(tmp_path / 'output'),
        ]
    )

    assert result == 1
    evidence = json.loads((report / 'cvm-catalog.json').read_text())
    assert evidence['status'] == 'failed'
    assert evidence['documents'][0]['publishedYearsNotSelected'] == [2004]
    assert json.loads(capsys.readouterr().err)['code'] == 'incomplete_catalog'


@pytest.mark.parametrize(
    'payload',
    [
        b'<p>no archive listing</p>',
        b'<a href="https://attacker.test/ipe_cia_aberta_2003.zip">bad</a>',
        b'<a href="../ipe_cia_aberta_2003.zip">bad</a>',
        b'<a href="other.zip">bad</a>',
    ],
)
def test_catalog_rejects_unrecognized_archive_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    """An official index cannot authorize another host or alternate path."""
    requests = _client(monkeypatch, payload)
    with pytest.raises(ValueError, match='Unrecognized CVM archive listing'):
        cvm_catalog.verify_catalog(_cases(tmp_path), 5)
    assert len(requests) == 1


def test_catalog_bounds_response_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The directory HTML cannot bypass the discovery memory budget."""
    _client(monkeypatch, b'x' * 100)
    monkeypatch.setattr(cvm_catalog, '_LISTING_LIMIT', 32)
    with pytest.raises(ValueError, match='byte limit'):
        cvm_catalog.verify_catalog(_cases(tmp_path), 5)


def test_catalog_preserves_network_failure_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP failure remains external evidence instead of an empty inventory."""
    _client(monkeypatch, b'unavailable', status=503)
    with pytest.raises(httpx.HTTPStatusError, match='503'):
        cvm_catalog.verify_catalog(_cases(tmp_path), 5)
