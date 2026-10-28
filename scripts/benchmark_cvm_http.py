"""Measure CVM HTTP download, validation, and extraction phases."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

if __name__ == '__main__' and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyarrow.parquet as pq

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    ParquetExtractorAdapterCVM,
)
from scripts.benchmark_cvm_http_support import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNKS,
    DEFAULT_PAYLOAD_MIB,
    MAX_PAYLOAD_MIB,
    PHASES,
    MeasuredDownloadAdapter,
    PhaseMeasurements,
    TimedParquetExtractor,
    build_fixture,
    serve_payload,
    track_httpx_client_construction,
)
from scripts.benchmark_support import schema_fingerprint


def _run_configuration(
    *,
    urls: Sequence[str],
    output_root: Path,
    chunk_size: int,
    repeat_index: int,
    source: str,
    expected_rows_per_file: int | None,
) -> dict[str, Any]:
    """Measure one batch, then validate its committed Parquet outputs."""
    measurements = PhaseMeasurements()
    output_dirs: list[Path] = []
    tasks: list[tuple[str, str, str, str]] = []
    batch_root = output_root / f'{chunk_size}-{repeat_index}'
    batch_root.mkdir()

    for index, url in enumerate(urls):
        destination = batch_root / f'destination-{index}'
        destination.mkdir()
        output_dirs.append(destination)
        tasks.append((url, 'DFP', str(2020 + index), str(destination)))

    extractor = TimedParquetExtractor(
        ParquetExtractorAdapterCVM(),
        measurements,
    )
    adapter = MeasuredDownloadAdapter(
        extractor,
        measurements,
        chunk_size=chunk_size,
        max_concurrent=len(urls),
    )
    started_at = time.perf_counter()
    with track_httpx_client_construction(measurements):
        result = asyncio.run(
            adapter.async_download_docs(
                tasks,
                automatic_extractor=True,
            )
        )
    elapsed_seconds = time.perf_counter() - started_at

    errors = dict(result.failed_downloads)
    parquet_files = sorted(
        path
        for destination in output_dirs
        for path in destination.glob('**/*.parquet')
    )
    output_rows = 0
    output_bytes = 0
    fingerprints: set[str] = set()
    artifact_digest = hashlib.sha256()
    for parquet_path in parquet_files:
        parquet = pq.ParquetFile(parquet_path)
        if parquet.metadata is None:
            errors[parquet_path.name] = 'Parquet metadata is unavailable'
            continue
        output_rows += parquet.metadata.num_rows
        output_bytes += parquet_path.stat().st_size
        fingerprints.add(schema_fingerprint(parquet.schema_arrow))
        artifact_digest.update(
            parquet_path.relative_to(batch_root).as_posix().encode()
        )
        with parquet_path.open('rb') as artifact:
            while chunk := artifact.read(1024 * 1024):
                artifact_digest.update(chunk)

    valid_rows = (
        expected_rows_per_file is None
        or output_rows == expected_rows_per_file * len(urls)
    )
    valid = (
        result.success_count_downloads == len(tasks)
        and result.error_count_downloads == 0
        and len(parquet_files) > 0
        and valid_rows
    )
    phase_snapshot = measurements.snapshot()
    phase_seconds = {
        name: float(values['seconds'])
        for name, values in phase_snapshot['phases'].items()
    }
    http_seconds = phase_seconds['get']
    client_initialization_seconds = phase_snapshot[
        'client_initialization_seconds'
    ]
    status = 'passed' if valid else 'failed'
    if _is_external_failure(source, errors):
        status = 'external_failure'

    return {
        'status': status,
        'source': source,
        'chunk_size_bytes': chunk_size,
        'repeat_index': repeat_index,
        'batch_size': len(tasks),
        'elapsed_seconds': elapsed_seconds,
        'phase_seconds': phase_seconds,
        'phase_bytes': phase_snapshot['phases'],
        'httpx_client_initializations': phase_snapshot[
            'client_initializations'
        ],
        'httpx_client_initialization_seconds': (client_initialization_seconds),
        'httpx_client_initialization_fraction_of_http_seconds': (
            client_initialization_seconds / http_seconds
            if http_seconds > 0
            else 0.0
        ),
        'successful_downloads': result.success_count_downloads,
        'failed_downloads': errors,
        'parquet_count': len(parquet_files),
        'parquet_rows': output_rows,
        'parquet_schema_fingerprints': sorted(fingerprints),
        'parquet_bytes': output_bytes,
        'parquet_artifact_sha256': (
            artifact_digest.hexdigest() if parquet_files else ''
        ),
    }


def _is_external_failure(
    source: str,
    errors: dict[str, str],
) -> bool:
    """Classify failed official downloads caused by unavailable networking."""
    network_markers = ('NetworkError:', 'DownloadTimeoutError:')
    return (
        source == 'official'
        and bool(errors)
        and all(
            any(marker in message for marker in network_markers)
            for message in errors.values()
        )
    )


def _median_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize elapsed and stage measurements for each chunk size."""
    summaries: list[dict[str, Any]] = []
    chunk_sizes = sorted(
        {int(record['chunk_size_bytes']) for record in records}
    )
    for chunk_size in chunk_sizes:
        selected = [
            record
            for record in records
            if record['chunk_size_bytes'] == chunk_size
            and record['status'] == 'passed'
        ]
        summaries.append(_median_record(chunk_size, selected))
    return summaries


def _median_record(
    chunk_size: int,
    selected: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize one chunk size or record that it has no successful runs."""
    if not selected:
        return {
            'chunk_size_bytes': chunk_size,
            'successful_repeats': 0,
            'status': 'failed',
        }

    summary: dict[str, Any] = {
        'chunk_size_bytes': chunk_size,
        'successful_repeats': len(selected),
        'elapsed_seconds_median': median(
            float(record['elapsed_seconds']) for record in selected
        ),
        'parquet_rows_median': median(
            int(record['parquet_rows']) for record in selected
        ),
        'parquet_bytes_median': median(
            int(record['parquet_bytes']) for record in selected
        ),
        'httpx_client_initializations_median': median(
            int(record['httpx_client_initializations']) for record in selected
        ),
        'httpx_client_initialization_seconds_median': median(
            float(record['httpx_client_initialization_seconds'])
            for record in selected
        ),
        'status': 'passed',
        'phase_seconds_median': {},
        'phase_bytes_median': {},
    }
    for phase in PHASES:
        summary['phase_seconds_median'][phase] = median(
            float(record['phase_seconds'][phase]) for record in selected
        )
        summary['phase_bytes_median'][phase] = {
            key: median(
                int(record['phase_bytes'][phase][key]) for record in selected
            )
            for key in (
                'transferred_bytes',
                'processed_bytes',
                'announced_bytes',
            )
        }
    return summary


def _parser() -> argparse.ArgumentParser:
    """Create the local and optional official-source benchmark CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--source', choices=('local', 'official'), default='local'
    )
    parser.add_argument('--official-url', action='append', default=[])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument('--payload-mib', type=int, default=DEFAULT_PAYLOAD_MIB)
    parser.add_argument(
        '--chunk-size',
        type=int,
        action='append',
        choices=DEFAULT_CHUNKS,
        default=None,
    )
    parser.add_argument('--output', type=Path)
    return parser


def _validate_arguments(arguments: argparse.Namespace) -> None:
    """Reject invalid sizes before generating data or networking."""
    if arguments.repeats < 1:
        raise SystemExit('--repeats must be at least one')
    if arguments.batch_size < 1:
        raise SystemExit('--batch-size must be at least one')
    if arguments.payload_mib < 1:
        raise SystemExit('--payload-mib must be at least one')
    if arguments.payload_mib > MAX_PAYLOAD_MIB:
        raise SystemExit(f'--payload-mib cannot exceed {MAX_PAYLOAD_MIB}')
    if arguments.source == 'official' and not arguments.official_url:
        raise SystemExit(
            '--source official requires at least one --official-url'
        )
    if arguments.source == 'local' and arguments.official_url:
        raise SystemExit('--official-url requires --source official')


def _run_batches(
    *,
    root: Path,
    chunk_sizes: Sequence[int],
    repeats: int,
    source: str,
    urls: Sequence[str],
    expected_rows: int | None,
) -> list[dict[str, Any]]:
    """Execute each chunk and repeat against the selected source batch."""
    return [
        _run_configuration(
            urls=urls,
            output_root=root,
            chunk_size=chunk_size,
            repeat_index=repeat_index,
            source=source,
            expected_rows_per_file=expected_rows,
        )
        for chunk_size in chunk_sizes
        for repeat_index in range(repeats)
    ]


def main() -> int:
    """Run all requested chunk sizes against a local or official CVM source."""
    arguments = _parser().parse_args()
    _validate_arguments(arguments)
    chunk_sizes = tuple(arguments.chunk_size or DEFAULT_CHUNKS)
    with TemporaryDirectory(prefix='gdf-cvm-http-benchmark-') as temporary:
        root = Path(temporary)
        if arguments.source == 'local':
            archive_payload, _csv_bytes, expected_rows = build_fixture(
                arguments.payload_mib
            )
            with serve_payload(archive_payload) as local_url:
                records = _run_batches(
                    root=root,
                    chunk_sizes=chunk_sizes,
                    repeats=arguments.repeats,
                    source='local',
                    urls=(local_url,) * arguments.batch_size,
                    expected_rows=expected_rows,
                )
            source_identity = archive_payload
            batch_size = arguments.batch_size
        else:
            urls = tuple(arguments.official_url)
            records = _run_batches(
                root=root,
                chunk_sizes=chunk_sizes,
                repeats=arguments.repeats,
                source='official',
                urls=urls,
                expected_rows=None,
            )
            source_identity = '\n'.join(urls).encode()
            batch_size = len(urls)

    record_statuses = {record['status'] for record in records}
    status = (
        'external_failure'
        if 'external_failure' in record_statuses
        else 'failed'
        if 'failed' in record_statuses
        else 'passed'
    )
    payload = {
        'schema_version': 1,
        'timestamp': datetime.now(UTC).isoformat(),
        'source': arguments.source,
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count() or 1,
        'source_identity_sha256': hashlib.sha256(source_identity).hexdigest(),
        'chunk_sizes_bytes': list(chunk_sizes),
        'repeats': arguments.repeats,
        'batch_size': batch_size,
        'records': records,
        'medians': _median_records(records),
        'status': status,
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True) + '\n'
    if arguments.output is None:
        print(serialized, end='')
    else:
        arguments.output.write_text(serialized, encoding='utf-8')
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
