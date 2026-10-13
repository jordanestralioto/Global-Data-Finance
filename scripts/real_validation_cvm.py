"""Execute and inspect one real CVM document/year case."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
)
from globaldatafinance.macro_exceptions import SecurityError

from .cvm_archive_oracle import reconcile_archive
from .real_validation_matrix.cases import canonical_cvm_case
from .real_validation_types import (
    ExternalFailure,
    NotPublished,
    ValidationCase,
)
from .real_validation_utils import (
    failed_details,
    is_external_message,
    sha256_file,
    temporary_paths,
)

_CVM_ENDPOINT_HOST = 'dados.cvm.gov.br'


class _CvmExtractor(Protocol):
    """Minimal extraction contract used to capture consumed ZIP evidence."""

    def extract(self, source_path: str, destination_path: str) -> None:
        """Extract one downloaded CVM ZIP file."""


class _EvidenceCapturingExtractor:
    """Capture the exact archive immediately before the facade extracts it."""

    def __init__(self, extractor: _CvmExtractor) -> None:
        self._extractor = extractor
        self.evidence: dict[str, int | str] | None = None
        self.reconciliation: dict[str, Any] | None = None

    def extract(self, source_path: str, destination_path: str) -> None:
        source = Path(source_path)
        expected_size = source.stat().st_size
        expected_sha256 = sha256_file(source)
        self.evidence = {
            'size_bytes': expected_size,
            'sha256': expected_sha256,
        }
        self.reconciliation = None
        self._extractor.extract(source_path, destination_path)
        destination = Path(destination_path)
        reconciliation = reconcile_archive(source, destination)
        _validate_archive_receipt(
            source,
            destination,
            reconciliation,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
        self.reconciliation = reconciliation


def _validate_archive_receipt(
    source: Path,
    destination: Path,
    reconciliation: dict[str, Any],
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    """Bind campaign evidence to the ZIP consumed by every Parquet writer."""
    if (
        source.stat().st_size != expected_size
        or sha256_file(source) != expected_sha256
    ):
        raise ValueError('CVM archive receipt changed during extraction')
    for member in reconciliation['members']:
        if not member['isCsv']:
            continue
        path = destination / member['parquetName']
        with pq.ParquetFile(path) as parquet:
            metadata = parquet.schema_arrow.metadata or {}
        if metadata.get(b'cvm.source-archive-sha256') != (
            expected_sha256.encode('ascii')
        ):
            raise ValueError(f'CVM archive receipt differs from {path.name}')


def execute_cvm_case(
    case: ValidationCase, workspace: Path, timeout: float
) -> dict[str, Any]:
    """Probe one canonical endpoint, then validate the public facade result."""
    case = canonical_cvm_case(case, case.output_root)
    probe_official_endpoint(case, timeout)
    output_directory = workspace / 'output'
    facade = FundamentalStocksDataCVM()
    evidence_extractor = _configure_campaign_facade(facade)
    try:
        result = facade.download(
            destination_path=str(output_directory),
            list_docs=[case.document or ''],
            initial_year=case.year,
            last_year=case.year,
            automatic_extractor=True,
        )
    except (
        CvmError,
        OSError,
        RuntimeError,
        SecurityError,
        TypeError,
        ValueError,
        httpx.HTTPError,
        pa.ArrowException,
    ) as error:
        message = f'CVM facade raised {type(error).__name__}: {error}'
        status = (
            'external_failure' if is_external_message(message) else 'failed'
        )
        return {
            **failed_details(None, message),
            'status': status,
            'published': True,
            **_evidence_fields(evidence_extractor.evidence),
        }
    public_result = {
        'successful_downloads': list(result.successful_downloads),
        'failed_downloads': dict(result.failed_downloads),
        'success_count_downloads': result.success_count_downloads,
        'error_count_downloads': result.error_count_downloads,
        'elapsed_time': result.elapsed_time,
    }
    details = validate_result(result, output_directory, case)
    if not details['valid']:
        status = (
            'external_failure'
            if is_external_message(details['message'])
            else 'failed'
        )
        return {
            **failed_details(public_result, details['message']),
            'status': status,
            'published': True,
            **_evidence_fields(evidence_extractor.evidence),
        }
    return {
        'status': 'passed',
        'message': 'CVM download and Parquet validation passed',
        'publicResult': public_result,
        'published': True,
        **_evidence_fields(evidence_extractor.evidence),
        'artifactCount': len(details['artifacts']),
        'artifacts': details['artifacts'],
        'recordCount': details['record_count'],
        'schema': details['schema'],
        'sourceReconciliation': evidence_extractor.reconciliation,
    }


def _configure_campaign_facade(
    facade: FundamentalStocksDataCVM,
) -> _EvidenceCapturingExtractor:
    """Disable redirect following and attach evidence to the public facade."""
    download_adapter = facade.download_adapter
    download_adapter.requests_adapter.follow_redirects = False
    delegate = download_adapter.file_extractor_repository
    if delegate is None:
        delegate = download_extraction.resolve_parquet_extractor(
            delegate,
            archive_limits=download_adapter.archive_limits,
            allowed_unc_roots=download_adapter.allowed_unc_roots,
        )
    extractor = _EvidenceCapturingExtractor(cast(_CvmExtractor, delegate))
    download_adapter.file_extractor_repository = cast(Any, extractor)
    return extractor


def probe_official_endpoint(case: ValidationCase, timeout: float) -> None:
    """Classify publication status without downloading an archive body."""
    url = case.url
    if not url:
        raise ValueError('CVM case has no official endpoint URL')
    _validate_official_endpoint(case)
    try:
        with (
            httpx.Client(timeout=timeout, follow_redirects=False) as client,
            client.stream('GET', url) as response,
        ):
            if response.status_code in {404, 410}:
                raise NotPublished(
                    f'official endpoint returned HTTP {response.status_code}'
                )
            if response.status_code != 200:
                raise ExternalFailure(
                    f'official endpoint returned HTTP {response.status_code}'
                )
    except NotPublished:
        raise
    except (httpx.TimeoutException, httpx.RequestError, OSError) as error:
        raise ExternalFailure(f'CVM endpoint unavailable: {error}') from error


def _validate_official_endpoint(case: ValidationCase) -> None:
    """Reject endpoint syntax that can escape the official CVM origin."""
    if case.url is None or case.document is None:
        raise ValueError('CVM case has no official endpoint URL')
    try:
        parsed = urlsplit(case.url)
        port = parsed.port
    except ValueError as error:
        raise ValueError('CVM endpoint has an invalid port') from error
    if (
        parsed.scheme != 'https'
        or parsed.hostname != _CVM_ENDPOINT_HOST
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path
        != (
            '/dados/CIA_ABERTA/DOC/'
            f'{case.document}/DADOS/'
            f'{case.document.lower()}_cia_aberta_{case.year}.zip'
        )
    ):
        raise ValueError('CVM endpoint is not an exact official HTTPS origin')


def _evidence_fields(
    evidence: dict[str, int | str] | None,
) -> dict[str, int | str]:
    """Return only evidence captured from an archive the facade consumed."""
    if evidence is None:
        return {}
    return {
        'inputSizeBytes': evidence['size_bytes'],
        'inputSha256': evidence['sha256'],
    }


def validate_result(
    result: Any, output_directory: Path, case: ValidationCase
) -> dict[str, Any]:
    """Reconcile the public CVM result with persisted Parquet artifacts."""
    public_error = validate_public_result(result)
    if public_error:
        return {'valid': False, 'message': public_error}
    parquet_files = sorted(output_directory.rglob('*.parquet'))
    if not parquet_files:
        return {'valid': False, 'message': 'CVM produced no Parquet files'}
    inspected = inspect_parquet_files(parquet_files, output_directory)
    if isinstance(inspected, str):
        return {'valid': False, 'message': inspected}
    artifacts, record_count, schema = inspected
    cleanup_error = validate_cleanup(output_directory)
    if cleanup_error:
        return {'valid': False, 'message': cleanup_error}
    if not case.document:
        return {'valid': False, 'message': 'CVM document is missing'}
    if result.successful_downloads != [f'{case.document}_{case.year}']:
        return {
            'valid': False,
            'message': 'CVM successful document identity does not match case',
        }
    return {
        'valid': True,
        'message': '',
        'artifacts': artifacts,
        'record_count': record_count,
        'schema': schema,
    }


def validate_public_result(result: Any) -> str | None:
    """Validate the public CVM counters and failed-download collection."""
    if (
        result.success_count_downloads != 1
        or result.error_count_downloads != 0
        or result.failed_downloads
    ):
        errors = '; '.join(
            f'{key}: {value}' for key, value in result.failed_downloads.items()
        )
        return f'CVM public result has errors: {errors or "no success"}'
    return None


def inspect_parquet_files(
    parquet_files: list[Path], output_directory: Path
) -> tuple[list[dict[str, Any]], int, dict[str, str]] | str:
    """Read every CVM Parquet through PyArrow and collect evidence."""
    artifacts: list[dict[str, Any]] = []
    record_count = 0
    schema: dict[str, str] = {}
    try:
        for parquet_file in parquet_files:
            parquet = pq.ParquetFile(
                parquet_file, page_checksum_verification=True
            )
            metadata = parquet.metadata
            if (
                metadata is None
                or metadata.num_rows < 0
                or metadata.num_columns == 0
            ):
                return f'Invalid or empty CVM Parquet: {parquet_file}'
            read_rows = sum(
                batch.num_rows
                for batch in parquet.iter_batches(batch_size=65_536)
            )
            if read_rows != metadata.num_rows:
                return f'PyArrow row count mismatch: {parquet_file}'
            record_count += metadata.num_rows
            relative = parquet_file.relative_to(output_directory).as_posix()
            artifacts.append(
                {
                    'path': relative,
                    'sizeBytes': parquet_file.stat().st_size,
                    'rows': metadata.num_rows,
                    'pyarrowReadable': True,
                    'metadataPresent': True,
                }
            )
            for field in parquet.schema_arrow:
                schema[f'{relative}:{field.name}'] = str(field.type)
    except (OSError, RuntimeError, ValueError) as error:
        return f'CVM Parquet validation failed: {error}'
    return artifacts, record_count, schema


def validate_cleanup(output_directory: Path) -> str | None:
    """Allow retained sources and reject leaked staging or writer state."""
    temporary = temporary_paths(output_directory)
    if temporary:
        return f'CVM temporary files leaked: {temporary}'
    return None
