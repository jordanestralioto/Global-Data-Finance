"""Deterministic tests for the isolated CVM validator."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import replace
from os import sep
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.real_validation_cvm as cvm
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
)
from scripts.real_validation_types import (
    ExternalFailure,
    NotPublished,
    ValidationCase,
)

pytestmark = pytest.mark.unit


def _cvm_case(document: str | None = 'DFP') -> ValidationCase:
    """Build one canonical CVM case for the 2024 DFP matrix entry."""
    document_name = document or 'DFP'
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/'
        f'{document_name}/DADOS/{document_name.lower()}_cia_aberta_2024.zip'
    )
    return ValidationCase(
        case_id=f'cvm-{document_name}-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=str(Path(sep, 'tmp', 'cvm-output')),
        document=document,
        mode='cvm',
        url=url,
    )


def _valid_zip_bytes() -> bytes:
    """Return a small safe ZIP payload for the consumed-archive boundary."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('DFP_2024.csv', b'id\n1\n')
    return buffer.getvalue()


class _Response:
    """Minimal response replacement for the endpoint status probe."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Client:
    """Minimal ``httpx.Client`` replacement with a controlled response."""

    def __init__(self, response: _Response, kwargs: dict[str, object]) -> None:
        self.response = response
        self.kwargs = kwargs
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str) -> _Response:
        self.calls.append((method, url))
        return self.response


def _patch_probe_client(
    monkeypatch: pytest.MonkeyPatch, response: _Response
) -> list[_Client]:
    """Install a no-network HTTP probe and return its constructed clients."""
    clients: list[_Client] = []

    def factory(**kwargs: object) -> _Client:
        client = _Client(response, kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(cvm.httpx, 'Client', factory)
    return clients


def _facade_adapter() -> SimpleNamespace:
    """Build the facade-owned collaborators the campaign configures."""

    class Delegate:
        def extract(self, source_path: str, destination_path: str) -> None:
            _ = source_path
            destination = Path(destination_path)
            destination.mkdir(parents=True, exist_ok=True)
            pq.write_table(
                pa.table({'id': [1, 2]}), destination / 'data.parquet'
            )

    return SimpleNamespace(
        requests_adapter=SimpleNamespace(follow_redirects=True),
        file_extractor_repository=Delegate(),
    )


def test_probe_accepts_canonical_http_200_without_persisting_a_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status probe never writes an independently downloaded ZIP."""
    case = _cvm_case()
    clients = _patch_probe_client(monkeypatch, _Response(200))

    cvm._probe_official_endpoint(case, timeout=4.0)

    assert clients[0].kwargs['follow_redirects'] is False
    assert clients[0].calls == [('GET', case.url or '')]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('status_code', [404, 410])
def test_probe_classifies_unpublished_cvm_archives(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    """HTTP 404 and 410 are absence of publication, not network errors."""
    case = _cvm_case()
    _patch_probe_client(monkeypatch, _Response(status_code))

    with pytest.raises(NotPublished, match=str(status_code)):
        cvm._probe_official_endpoint(case, 4.0)


def test_probe_classifies_other_http_status_as_external_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Classify redirects and other non-success statuses as external errors."""
    case = _cvm_case()
    clients = _patch_probe_client(monkeypatch, _Response(302))

    with pytest.raises(ExternalFailure, match='302'):
        cvm._probe_official_endpoint(case, 4.0)

    assert len(clients) == 1
    assert clients[0].calls == [('GET', case.url or '')]


@pytest.mark.parametrize(
    'error_type', [httpx.RequestError, httpx.TimeoutException]
)
def test_probe_classifies_network_and_timeout_failures(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    """DNS/request and timeout failures remain explicitly external."""
    case = _cvm_case()
    request = httpx.Request('GET', case.url or '')
    network_error = cast(Any, error_type)(
        'network unavailable', request=request
    )

    class FailingClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> FailingClient:
            raise network_error

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(cvm.httpx, 'Client', FailingClient)

    with pytest.raises(ExternalFailure, match='endpoint unavailable'):
        cvm._probe_official_endpoint(case, 4.0)


def test_probe_rejects_missing_and_nonofficial_urls_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed endpoint cannot construct an HTTP client or request body."""
    constructed = False

    def fail_client(**_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError('HTTP client must not be constructed')

    monkeypatch.setattr(cvm.httpx, 'Client', fail_client)

    with pytest.raises(ValueError, match='no official endpoint'):
        cvm._probe_official_endpoint(replace(_cvm_case(), url=None), 4.0)
    for url in (
        'http://127.0.0.1/metadata',
        (_cvm_case().url or '').replace('https://', 'https://operator@'),
        (_cvm_case().url or '').replace(
            'dados.cvm.gov.br', 'dados.cvm.gov.br:444'
        ),
        (_cvm_case().url or '').replace(
            'dfp_cia_aberta_2024.zip', 'other.zip'
        ),
    ):
        with pytest.raises(ValueError, match='exact official HTTPS origin'):
            cvm._probe_official_endpoint(replace(_cvm_case(), url=url), 4.0)

    assert constructed is False


def test_execute_rejects_manifest_url_before_constructing_http_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered resume case never reaches the CVM HTTP boundary."""
    malicious = replace(
        _cvm_case(),
        input_path='http://127.0.0.1/internal',
        url='http://127.0.0.1/internal',
    )
    constructed = False

    def fail_client(**_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError('HTTP client must not be constructed')

    monkeypatch.setattr(cvm.httpx, 'Client', fail_client)

    with pytest.raises(ValueError, match='official matrix'):
        cvm.execute_cvm_case(malicious, tmp_path / 'workspace', 4.0)

    assert constructed is False


def test_execute_cvm_case_records_hash_of_archive_consumed_by_facade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Campaign evidence is captured immediately before public extraction."""
    case = _cvm_case()
    workspace = tmp_path / 'workspace'
    payload = _valid_zip_bytes()
    monkeypatch.setattr(cvm, '_probe_official_endpoint', lambda *_args: None)

    class Facade:
        instance: Facade

        def __init__(self) -> None:
            self.download_adapter = _facade_adapter()
            Facade.instance = self

        def download(self, **_kwargs: object) -> DownloadResultCVM:
            source = workspace / 'consumed.zip'
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(payload)
            self.download_adapter.file_extractor_repository.extract(
                str(source), str(workspace / 'output')
            )
            return DownloadResultCVM(successful_downloads=['DFP_2024'])

    monkeypatch.setattr(cvm, 'FundamentalStocksDataCVM', Facade)

    result = cvm.execute_cvm_case(case, workspace, 4.0)

    assert result['status'] == 'passed'
    assert result['recordCount'] == 2
    assert result['artifactCount'] == 1
    assert result['inputSizeBytes'] == len(payload)
    assert result['inputSha256'] == hashlib.sha256(payload).hexdigest()
    assert (
        Facade.instance.download_adapter.requests_adapter.follow_redirects
        is False
    )


@pytest.mark.parametrize(
    ('raised', 'expected_status'),
    [
        (CvmError('invalid document'), 'failed'),
        (RuntimeError('DNS unavailable'), 'external_failure'),
    ],
)
def test_execute_cvm_case_classifies_facade_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
    expected_status: str,
) -> None:
    """Facade failures retain their cause and network classification."""
    case = _cvm_case()
    workspace = tmp_path / 'workspace'
    monkeypatch.setattr(cvm, '_probe_official_endpoint', lambda *_args: None)

    class Facade:
        def __init__(self) -> None:
            self.download_adapter = _facade_adapter()

        def download(self, **_kwargs: object) -> DownloadResultCVM:
            raise raised

    monkeypatch.setattr(cvm, 'FundamentalStocksDataCVM', Facade)

    result = cvm.execute_cvm_case(case, workspace, 4.0)

    assert result['status'] == expected_status
    assert str(raised) in result['message']
    assert result['publicResult'] is None
    assert 'inputSha256' not in result


def test_execute_cvm_case_classifies_partial_public_result_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A public result with failed downloads cannot be approved."""
    case = _cvm_case()
    workspace = tmp_path / 'workspace'
    monkeypatch.setattr(cvm, '_probe_official_endpoint', lambda *_args: None)

    class Facade:
        def __init__(self) -> None:
            self.download_adapter = _facade_adapter()

        def download(self, **_kwargs: object) -> DownloadResultCVM:
            return DownloadResultCVM(
                successful_downloads=['DFP_2024'],
                failed_downloads={'DFP_2024': 'invalid CSV'},
            )

    monkeypatch.setattr(cvm, 'FundamentalStocksDataCVM', Facade)

    result = cvm.execute_cvm_case(case, workspace, 4.0)

    assert result['status'] == 'failed'
    assert 'invalid CSV' in result['message']


def test_validate_result_requires_document_after_artifact_checks(
    tmp_path: Path,
) -> None:
    """A valid artifact without a document identity is not reportable."""
    output = tmp_path / 'output'
    output.mkdir()
    pq.write_table(pa.table({'id': [1]}), output / 'data.parquet')
    result = DownloadResultCVM(successful_downloads=['unknown'])

    details = cvm._validate_result(result, output, _cvm_case(None))

    assert details == {'valid': False, 'message': 'CVM document is missing'}


def test_validate_result_rejects_no_parquet_and_invalid_public_counters(
    tmp_path: Path,
) -> None:
    """No artifact or failed public counters can be approved."""
    output = tmp_path / 'empty'
    output.mkdir()
    no_files = cvm._validate_result(
        DownloadResultCVM(successful_downloads=['DFP_2024']),
        output,
        _cvm_case(),
    )
    failed_public = cvm._validate_public_result(
        DownloadResultCVM(failed_downloads={'DFP_2024': 'bad'})
    )

    assert no_files == {
        'valid': False,
        'message': 'CVM produced no Parquet files',
    }
    assert failed_public == 'CVM public result has errors: DFP_2024: bad'


def test_inspect_parquet_files_reads_metadata_and_counts_batches(
    tmp_path: Path,
) -> None:
    """PyArrow inspection records rows and schema for every CVM file."""
    output = tmp_path / 'output'
    output.mkdir()
    first = output / 'first.parquet'
    second = output / 'nested' / 'second.parquet'
    second.parent.mkdir()
    pq.write_table(pa.table({'id': [1, 2]}), first)
    pq.write_table(pa.table({'value': ['x']}), second)

    inspected = cvm._inspect_parquet_files([first, second], output)

    assert not isinstance(inspected, str)
    artifacts, records, schema = inspected
    assert len(artifacts) == 2
    assert records == 3
    assert 'first.parquet:id' in schema
    assert 'nested/second.parquet:value' in schema


@pytest.mark.parametrize('kind', ['empty', 'unreadable', 'row_count'])
def test_inspect_parquet_files_rejects_invalid_evidence(
    tmp_path: Path, kind: str
) -> None:
    """Empty, unreadable, and inconsistent Parquet evidence is rejected."""
    output = tmp_path / 'output'
    output.mkdir()
    path = output / 'data.parquet'
    if kind == 'empty':
        pq.write_table(pa.table({'id': pa.array([], type=pa.int64())}), path)
    elif kind == 'unreadable':
        path.write_bytes(b'not parquet')
    else:
        pq.write_table(pa.table({'id': [1]}), path)

        class FakeParquet:
            metadata = SimpleNamespace(num_rows=2)
            schema_arrow = pa.schema([('id', pa.int64())])

            def iter_batches(self, **kwargs: int):
                assert kwargs['batch_size'] == 65_536
                return [SimpleNamespace(num_rows=1)]

        original = cvm.pq.ParquetFile
        cvm.pq.ParquetFile = lambda _candidate: FakeParquet()
        try:
            inspected = cvm._inspect_parquet_files([path], output)
        finally:
            cvm.pq.ParquetFile = original
        assert isinstance(inspected, str)
        assert 'row count mismatch' in inspected
        return

    inspected = cvm._inspect_parquet_files([path], output)

    assert isinstance(inspected, str)
    assert 'Invalid or empty' in inspected or 'validation failed' in inspected


def test_validate_cleanup_rejects_archives_and_temporary_markers(
    tmp_path: Path,
) -> None:
    """CVM output cleanup must remove archives and staging-like paths."""
    output = tmp_path / 'output'
    output.mkdir()
    (output / 'source.zip').touch()
    assert cvm._validate_cleanup(output) == 'CVM source ZIP was not cleaned up'
    (output / 'source.zip').unlink()
    (output / 'staging.tmp').touch()

    cleanup_error = cvm._validate_cleanup(output)
    assert cleanup_error is not None
    assert 'temporary files leaked' in cleanup_error


def test_cvm_sha256_file_is_deterministic(tmp_path: Path) -> None:
    """The consumed archive digest is stable for identical bytes."""
    path = tmp_path / 'payload.bin'
    path.write_bytes(b'abc')

    assert cvm._sha256_file(path) == hashlib.sha256(b'abc').hexdigest()
