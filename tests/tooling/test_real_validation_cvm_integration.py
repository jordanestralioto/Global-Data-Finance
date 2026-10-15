"""Real CVM facade wiring behind a deterministic HTTP transport."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.real_validation_cvm as cvm
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_infra.transactional_publication import (
    TransactionalPublisher,
)
from scripts.real_validation_types import ValidationCase
from scripts.real_validation_utils import temporary_paths

pytestmark = pytest.mark.integration


def _case(root: Path) -> ValidationCase:
    """Build a canonical document case with a caller-owned output root."""
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        'dfp_cia_aberta_2024.zip'
    )
    return ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=str(root),
        document='DFP',
        mode='cvm',
        url=url,
    )


@pytest.mark.parametrize('contents', [b'id\n1\n2\n', b'id\n'])
def test_real_facade_initializes_lazy_extractor_and_validates_all_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: bytes
) -> None:
    """Default facade wiring succeeds for data and valid header-only files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('dfp_cia_aberta_2024.csv', contents)
    payload = buffer.getvalue()
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        return httpx.Response(
            200,
            headers={'content-length': str(len(payload))},
            content=payload if request.method == 'GET' else b'',
        )

    original_client = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(respond), **kwargs
        )

    monkeypatch.setattr(httpx, 'AsyncClient', client)
    monkeypatch.setattr(cvm, 'probe_official_endpoint', lambda *_args: None)

    result = cvm.execute_cvm_case(_case(tmp_path), tmp_path / 'workspace', 5)

    assert result['status'] == 'passed'
    assert result['inputSha256'] == hashlib.sha256(payload).hexdigest()
    assert result['inputSizeBytes'] == len(payload)
    assert result['recordCount'] == (2 if contents.endswith(b'2\n') else 0)
    assert result['artifactCount'] == 1
    assert result['publicResult']['successful_downloads'] == ['DFP_2024']
    assert requests == ['GET', 'HEAD']
    output = tmp_path / 'workspace' / 'output'
    path = output / 'DFP' / '2024' / 'dfp_cia_aberta_2024.parquet'
    assert pq.ParquetFile(path).metadata.num_rows == result['recordCount']
    assert (path.parent / 'dfp_cia_aberta_2024.zip').read_bytes() == payload
    assert result['sourceReconciliation']['status'] == 'passed'
    assert (
        result['sourceReconciliation']['recordCount'] == result['recordCount']
    )


def test_campaign_rejects_success_identity_from_a_different_document(
    tmp_path: Path,
) -> None:
    """Correct counters cannot certify the wrong document or year."""
    pq.write_table(pa.table({'id': [1]}), tmp_path / 'data.parquet')
    result = DownloadResultCVM(successful_downloads=['FCA_2024'])

    validated = cvm.validate_result(result, tmp_path, _case(tmp_path))

    assert validated == {
        'valid': False,
        'message': 'CVM successful document identity does not match case',
    }


def test_campaign_detects_real_unfinished_publication_state(
    tmp_path: Path,
) -> None:
    """A live transaction cannot be mistaken for a clean case workspace."""
    publisher = TransactionalPublisher(tmp_path, owner='cvm')
    publication = publisher.begin()
    try:
        expected = {
            publication.staging_dir.relative_to(tmp_path).as_posix(),
            publication.manifest_path.name,
            publisher.lock_dir.name,
        }
        assert expected <= set(temporary_paths(tmp_path))
    finally:
        publication.abort()
    assert temporary_paths(tmp_path) == []


@pytest.mark.parametrize(
    'change', ['same_values', 'different_values', 'metadata']
)
def test_campaign_archive_receipt_must_match_consumed_parquet_origin(
    tmp_path: Path, change: str
) -> None:
    """Readable matching rows cannot certify a different consumed ZIP hash."""
    source = tmp_path / 'source.zip'
    replacement = tmp_path / 'replacement.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', b'value\noriginal\n')
    with zipfile.ZipFile(replacement, 'w') as archive:
        archive.comment = b'another archive revision'
        archive.writestr(
            'data.csv',
            b'value\nreplacement\n'
            if change == 'different_values'
            else b'value\noriginal\n',
        )
    original_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    class ChangingExtractor:
        def extract(self, source_path: str, destination_path: str) -> None:
            if change != 'metadata':
                replacement.replace(source)
            ParquetExtractorAdapterCVM().extract(source_path, destination_path)
            if change == 'metadata':
                path = Path(destination_path) / 'data.parquet'
                table = pq.read_table(path)
                metadata = dict(table.schema.metadata or {})
                metadata[b'cvm.source-archive-sha256'] = b'0' * 64
                pq.write_table(table.replace_schema_metadata(metadata), path)

    extractor = cvm._EvidenceCapturingExtractor(ChangingExtractor())
    with pytest.raises(ValueError, match='archive receipt'):
        extractor.extract(str(source), str(tmp_path))
    assert extractor.evidence is not None
    assert extractor.evidence['sha256'] == original_sha256
    assert extractor.reconciliation is None
