"""Child-process operations and result aggregation for ingestion benchmarks."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import zipfile
from collections.abc import Callable, Iterable
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from statistics import median
from typing import Any

from globaldatafinance.macro_exceptions import ExtractionError
from scripts.benchmark_support import (
    MEBIBYTE,
    RssSampler,
    ScenarioInput,
    base_record,
    digest_parquet_rows,
    schema_fingerprint,
    unmeasured_record,
    verify_input_digest,
    write_json,
)
from scripts.process_runner import ProcessRunnerError, run_process

OperationResult = tuple[int, str, bool, int, float, str]
ChildOperation = Callable[[ScenarioInput, Path], OperationResult]

_OPERATIONAL_ERRORS = (
    ExtractionError,
    OSError,
    ValueError,
    RuntimeError,
    zipfile.BadZipFile,
)

_pq: Any = None


def _get_pq() -> Any:
    """Return ``pyarrow.parquet``, importing lazily on first call."""
    global _pq
    if _pq is None:
        import pyarrow.parquet as pq

        _pq = pq
    return _pq


def validate_cvm_output(
    output_dir: Path,
    source: ScenarioInput,
) -> tuple[int, str, bool, int, str]:
    """Validate a generated CVM artifact's typed logical rows and schema."""
    outputs = sorted(output_dir.glob('*.parquet'))
    if len(outputs) != 1:
        return 0, '', False, 0, ''
    parquet = _get_pq().ParquetFile(outputs[0])
    if parquet.metadata is None:
        return 0, '', False, 0, ''
    digest, first, last = digest_parquet_rows(
        parquet, batch_size=50_000, boundary_column='identificador'
    )
    valid = (
        parquet.metadata.num_rows == source.row_count
        and first == source.expected_first
        and last == source.expected_last
        and b'pandas' not in (parquet.schema_arrow.metadata or {})
        and (not source.expected_digest or digest == source.expected_digest)
    )
    return (
        parquet.metadata.num_rows,
        schema_fingerprint(parquet.schema_arrow),
        valid,
        outputs[0].stat().st_size,
        digest,
    )


def validate_b3_output(
    output: Path,
    source: ScenarioInput,
) -> tuple[int, str, bool, int, str]:
    """Validate B3 schema, row order, count, and typed output."""
    parquet = _get_pq().ParquetFile(output)
    if parquet.metadata is None:
        return 0, '', False, 0, ''
    cols = None if source.expected_digest else ['ticker']
    digest, first, last = digest_parquet_rows(
        parquet, batch_size=200_000, boundary_column='ticker', columns=cols
    )
    if not source.expected_digest:
        digest = ''
    from globaldatafinance.brazil.b3_data import historical_quotes

    valid = (
        parquet.schema_arrow
        == historical_quotes.parquet_writer.build_b3_schema()
        and (
            parquet.metadata.num_rows == source.row_count
            if source.row_count
            else parquet.metadata.num_rows > 0
        )
        and (not source.expected_first or first == source.expected_first)
        and (not source.expected_last or last == source.expected_last)
        and (source.row_count > 0 or bool(first and last))
        and (not source.expected_digest or digest == source.expected_digest)
    )
    return (
        parquet.metadata.num_rows,
        schema_fingerprint(parquet.schema_arrow),
        valid,
        output.stat().st_size,
        digest,
    )


def run_cvm(source: ScenarioInput, output_dir: Path) -> OperationResult:
    """Run the production CVM transaction over one generated ZIP."""
    from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
        transaction,
    )

    if source.path is None:
        raise ValueError('CVM benchmark requires a source ZIP')
    output_dir.mkdir()
    started = time.perf_counter()
    with zipfile.ZipFile(source.path, 'r') as archive:
        transaction.CvmFailureAtomicBatchCommit(
            str(source.path), str(output_dir)
        ).execute(archive)
    op_sec = time.perf_counter() - started
    rows, fp, eq, out_bytes, digest = validate_cvm_output(output_dir, source)
    return rows, fp, eq, out_bytes, op_sec, digest


def run_b3(source: ScenarioInput, output_dir: Path) -> OperationResult:
    """Run the public B3 facade over generated or external input data."""
    from globaldatafinance import HistoricalQuotesB3

    if source.path is None:
        raise ValueError('B3 benchmark requires a source directory or TXT')
    input_dir = source.path if source.path.is_dir() else source.path.parent
    output_dir.mkdir()
    initial_year = 2008 if source.scenario == 'b3_annual' else 2024
    started = time.perf_counter()
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(input_dir),
        destination_path=str(output_dir),
        assets_list=['ações'],
        initial_year=initial_year,
        last_year=2024,
        output_filename='benchmark_quotes',
        processing_mode='fast',
        verbose=False,
    )
    if not result['success']:
        raise RuntimeError(f'B3 extraction failed: {result["errors"]}')
    op_sec = time.perf_counter() - started
    rows, fp, eq, out_bytes, digest = validate_b3_output(
        Path(result['output_file']), source
    )
    return rows, fp, eq, out_bytes, op_sec, digest


def _run_import_root() -> OperationResult:
    started = time.perf_counter()
    import globaldatafinance

    valid = globaldatafinance.__name__ == 'globaldatafinance' and not any(
        m == eng or m.startswith(f'{eng}.')
        for eng in ('pandas', 'numpy', 'polars', 'pyarrow')
        for m in sys.modules
    )
    return 0, '', valid, 0, time.perf_counter() - started, ''


def _run_runtime_footprint() -> OperationResult:
    started = time.perf_counter()
    total_bytes = 0
    for package in ('globaldatafinance', 'pandas', 'pyarrow'):
        try:
            installed = distribution(package)
        except PackageNotFoundError:
            return 0, '', False, 0, time.perf_counter() - started, ''
        for item in installed.files or []:
            candidate = Path(str(installed.locate_file(item)))
            if candidate.is_file():
                total_bytes += candidate.stat().st_size
    valid = importlib.util.find_spec('polars') is None
    return 0, '', valid, total_bytes, time.perf_counter() - started, ''


def execute_child_operation(
    source: ScenarioInput, output_dir: Path
) -> OperationResult:
    """Execute the appropriate child operation for the given scenario."""
    if source.scenario == 'import_root':
        return _run_import_root()
    if source.scenario == 'runtime_footprint':
        return _run_runtime_footprint()
    if source.scenario.startswith('cvm'):
        return run_cvm(source, output_dir)
    return run_b3(source, output_dir)


def run_child(
    source: ScenarioInput,
    repeat_index: int,
    result_path: Path,
    *,
    operation: ChildOperation = execute_child_operation,
) -> None:
    """Execute one scenario in a fresh process and persist one JSON record."""
    if source.scenario == 'b3_annual' and source.path is None:
        write_json(
            result_path,
            unmeasured_record(
                source,
                repeat_index,
                status='skipped',
                reason='external corpus unavailable',
            ),
        )
        return

    try:
        verify_input_digest(source)
    except (OSError, ValueError) as error:
        write_json(
            result_path,
            unmeasured_record(
                source,
                repeat_index,
                status='failed',
                reason=f'{type(error).__name__}: {error}',
            ),
        )
        return

    sampler = RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        (rows, fp, eq, out_bytes, op_sec, digest) = operation(
            source, result_path.parent / 'output'
        )
        elapsed = time.perf_counter() - started
        after = sampler.stop()
        record = base_record(source, repeat_index)
        record.update(
            {
                'row_count': rows,
                'schema_fingerprint': fp,
                'logical_digest': digest,
                'logical_equivalence': eq,
                'elapsed_seconds': op_sec,
                'phase_seconds': {
                    'operation': op_sec,
                    'validation': max(0.0, elapsed - op_sec),
                },
                'rss_before_mib': sampler.before_bytes / MEBIBYTE,
                'rss_peak_mib': sampler.peak_bytes / MEBIBYTE,
                'rss_after_mib': after / MEBIBYTE,
                'output_bytes': out_bytes,
                'status': 'passed' if eq else 'failed',
            }
        )
    except _OPERATIONAL_ERRORS as error:
        elapsed = time.perf_counter() - started
        after = sampler.stop()
        record = unmeasured_record(
            source,
            repeat_index,
            status='failed',
            reason=f'{type(error).__name__}: {error}',
            elapsed_seconds=elapsed,
            rss_before_mib=sampler.before_bytes / MEBIBYTE,
            rss_peak_mib=sampler.peak_bytes / MEBIBYTE,
            rss_after_mib=after / MEBIBYTE,
        )
    write_json(result_path, record)


def child_command(
    source: ScenarioInput, repeat_index: int, result_path: Path
) -> list[str]:
    """Build an allowlisted process-runner command for one measurement."""
    child_script = Path(__file__).with_name('benchmark_ingestion.py').resolve()
    command = [
        'python',
        str(child_script),
        '--child',
        '--scenario',
        source.scenario,
        '--repeat-index',
        str(repeat_index),
        '--result-path',
        str(result_path),
        '--input-sha256',
        source.input_sha256,
        '--row-count',
        str(source.row_count),
        '--expected-first',
        source.expected_first,
        '--expected-last',
        source.expected_last,
        '--expected-digest',
        source.expected_digest,
    ]
    if source.path is not None:
        command.extend(['--input-path', str(source.path)])
    return command


def run_parent_scenario(
    source: ScenarioInput, repeats: int, root: Path, git_sha: str
) -> list[dict[str, Any]]:
    """Run each repeat in isolation with distinct corpus output paths."""
    records: list[dict[str, Any]] = []
    for repeat_index in range(repeats):
        result_dir = root / f'{source.scenario}-{repeat_index}'
        result_dir.mkdir()
        result_path = result_dir / 'result.json'
        command = child_command(source, repeat_index, result_path)
        try:
            process = run_process(command, cwd=Path.cwd(), check=False)
            if not result_path.is_file():
                reason = process.stderr.strip() or process.stdout.strip()
                records.append(
                    parent_failure_record(
                        source, repeat_index, git_sha, reason
                    )
                )
                continue
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            payload['git_sha'] = git_sha
            if process.returncode != 0:
                payload['status'] = 'failed'
                payload['reason'] = process.stderr.strip() or (
                    'benchmark child returned non-zero status'
                )
            records.append(payload)
        except (ProcessRunnerError, OSError, json.JSONDecodeError) as error:
            records.append(
                parent_failure_record(
                    source,
                    repeat_index,
                    git_sha,
                    f'{type(error).__name__}: {error}',
                )
            )
    return records


def parent_failure_record(
    source: ScenarioInput, repeat_index: int, git_sha: str, reason: str
) -> dict[str, Any]:
    """Report a failed child start using the benchmark JSON shape."""
    return unmeasured_record(
        source, repeat_index, status='failed', reason=reason, git_sha=git_sha
    )


def median_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize successful repeats without hiding failed measurements."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record.get('status') == 'passed':
            grouped.setdefault(str(record['scenario']), []).append(record)

    return [
        {
            'scenario': sc,
            'successful_repeats': len(recs),
            'elapsed_seconds_median': median(
                r['elapsed_seconds'] for r in recs
            ),
            'rss_peak_mib_median': median(r['rss_peak_mib'] for r in recs),
            'output_bytes_median': median(r['output_bytes'] for r in recs),
        }
        for sc, recs in sorted(grouped.items())
    ]
