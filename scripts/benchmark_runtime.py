"""Child-process operations and result aggregation for ingestion benchmarks."""

from __future__ import annotations

import importlib.util
import json
import os
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
    RssSampler,
    ScenarioInput,
    base_record,
    digest_parquet_rows,
    schema_fingerprint,
    sha256_file,
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
    if (
        len(outputs) != 1
        or (parquet := _get_pq().ParquetFile(outputs[0])).metadata is None
    ):
        return 0, '', False, 0, ''
    digest, first, last = digest_parquet_rows(
        parquet, batch_size=50_000, boundary_column='identificador'
    )
    row_count = parquet.metadata.num_rows
    valid = (
        row_count == source.row_count
        and (first, last) == (source.expected_first, source.expected_last)
        and b'pandas' not in (parquet.schema_arrow.metadata or {})
        and (not source.expected_digest or digest == source.expected_digest)
    )
    fp = schema_fingerprint(parquet.schema_arrow)
    return row_count, fp, valid, outputs[0].stat().st_size, digest


def validate_b3_output(
    output: Path,
    source: ScenarioInput,
) -> tuple[int, str, bool, int, str]:
    """Validate B3 schema, row order, count, and typed output."""
    if (parquet := _get_pq().ParquetFile(output)).metadata is None:
        return 0, '', False, 0, ''
    digest, first, last = digest_parquet_rows(
        parquet, batch_size=200_000, boundary_column='ticker'
    )
    from globaldatafinance.brazil.b3_data import historical_quotes

    nr = parquet.metadata.num_rows
    exp_rows = nr == source.row_count if source.row_count else nr > 0
    schema = historical_quotes.parquet_writer.build_b3_schema()
    valid = (
        parquet.schema_arrow == schema
        and exp_rows
        and (not source.expected_first or first == source.expected_first)
        and (not source.expected_last or last == source.expected_last)
        and (source.row_count > 0 or bool(first and last))
        and bool(source.expected_digest)
        and digest == source.expected_digest
    )
    fp = schema_fingerprint(parquet.schema_arrow)
    return nr, fp, valid, output.stat().st_size, digest


def run_cvm(source: ScenarioInput, output_dir: Path) -> OperationResult:
    """Run the production CVM transaction over one generated ZIP."""
    import globaldatafinance.brazil.cvm.fundamental_stocks_data as cvm_data

    if source.path is None:
        raise ValueError('CVM benchmark requires a source ZIP')
    output_dir.mkdir()
    started = time.perf_counter()
    with zipfile.ZipFile(source.path, 'r') as archive:
        cvm_data.transaction.CvmFailureAtomicBatchCommit(
            str(source.path), str(output_dir)
        ).execute(archive)
    op_sec = time.perf_counter() - started
    rows, fp, eq, out_bytes, digest = validate_cvm_output(output_dir, source)
    return rows, fp, eq, out_bytes, op_sec, digest


_last_b3_phase_timings: dict[str, Any] = {}


def run_b3(
    source: ScenarioInput,
    output_dir: Path,
    *,
    processing_mode: str = 'fast',
    executor_backend: str = 'thread',
) -> OperationResult:
    """Run the public B3 facade over generated or external input data."""
    global _last_b3_phase_timings
    from globaldatafinance import HistoricalQuotesB3

    if source.path is None:
        raise ValueError('B3 benchmark requires a source directory or TXT')
    input_dir = source.path if source.path.is_dir() else source.path.parent
    output_dir.mkdir()
    year_ranges = {
        'b3_multi_4x25k': (2021, 2020 + source.source_count),
        'b3_annual': (2000, 2026),
    }
    init_yr, last_yr = year_ranges.get(source.scenario, (2024, 2024))
    overrides = {
        'GDF_B3_EXECUTOR_BACKEND': executor_backend,
        'GDF_B3_WORKER_LIMIT': str(source.worker_limit),
    }
    previous_environment = {name: os.environ.get(name) for name in overrides}
    os.environ.update(overrides)
    try:
        started = time.perf_counter()
        client = HistoricalQuotesB3()
        result = client.extract(
            path_of_docs=str(input_dir),
            destination_path=str(output_dir),
            assets_list=['ações'],
            initial_year=init_yr,
            last_year=last_yr,
            output_filename='benchmark_quotes',
            processing_mode=processing_mode,
            verbose=False,
        )
        if not result['success']:
            raise RuntimeError(f'B3 extraction failed: {result["errors"]}')
        op_sec = time.perf_counter() - started
        _last_b3_phase_timings = dict(client._last_phase_timings)
    finally:
        for name, previous_value in previous_environment.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value
    output_path = Path(result['output_file'])
    rows, fp, eq, out_bytes, digest = validate_b3_output(output_path, source)
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
    started, total_bytes = time.perf_counter(), 0
    for pkg in ('globaldatafinance', 'pandas', 'pyarrow'):
        try:
            inst = distribution(pkg)
        except PackageNotFoundError:
            return 0, '', False, 0, time.perf_counter() - started, ''
        total_bytes += sum(
            c.stat().st_size
            for i in inst.files or []
            if (c := Path(str(inst.locate_file(i)))).is_file()
        )
    ok = importlib.util.find_spec('polars') is None
    return 0, '', ok, total_bytes, time.perf_counter() - started, ''


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
    return run_b3(
        source,
        output_dir,
        processing_mode=source.processing_mode,
        executor_backend=source.executor_backend,
    )


def run_child(
    source: ScenarioInput,
    repeat_index: int,
    result_path: Path,
    *,
    operation: ChildOperation = execute_child_operation,
) -> None:
    """Execute one scenario in a fresh process and persist one JSON record."""

    def _write_early(status: str, reason: str) -> None:
        write_json(
            result_path,
            unmeasured_record(
                source, repeat_index, status=status, reason=reason
            ),
        )

    if source.scenario == 'b3_annual' and source.path is None:
        _write_early('skipped', 'external corpus unavailable')
        return

    try:
        verify_input_digest(source)
    except (OSError, ValueError) as error:
        _write_early('failed', f'{type(error).__name__}: {error}')
        return
    sampler = RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        out_dir = result_path.parent / 'output'
        (rows, fp, eq, out_bytes, op_sec, digest) = operation(source, out_dir)
        elapsed = time.perf_counter() - started
        after = sampler.stop()
        phase_seconds: dict[str, Any] = {
            'operation': op_sec,
            'validation': max(0.0, elapsed - op_sec),
        }
        phase_seconds.update(_last_b3_phase_timings)
        b3_t = _last_b3_phase_timings
        pqs = list(out_dir.glob('*.parquet')) if out_dir.is_dir() else []
        parquet = pqs[0] if len(pqs) == 1 else None
        art_sha = sha256_file(parquet) if parquet and parquet.is_file() else ''
        record = base_record(source, repeat_index) | {
            'row_count': rows,
            'schema_fingerprint': fp,
            'logical_digest': digest,
            'artifact_sha256': art_sha,
            'logical_equivalence': eq,
            'elapsed_seconds': op_sec,
            'phase_seconds': phase_seconds,
            'output_bytes': out_bytes,
            'status': 'passed' if eq else 'failed',
            'effective_backend': b3_t.get(
                'effective_backend', source.executor_backend
            ),
            'effective_worker_limit': b3_t.get(
                'effective_worker_limit', source.worker_limit
            ),
            'effective_source_count': source.source_count,
            **sampler.to_record_metrics(after),
        }
        if not eq:
            record['reason'] = (
                'output not logically equivalent to benchmark expectation'
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
            **sampler.to_record_metrics(after),
        )
    write_json(result_path, record)


def child_command(
    source: ScenarioInput, repeat_index: int, result_path: Path
) -> list[str]:
    """Build an allowlisted process-runner command for one measurement."""
    child_script = Path(__file__).with_name('benchmark_ingestion.py').resolve()
    opts = {
        'scenario': source.scenario,
        'repeat-index': repeat_index,
        'result-path': result_path,
        'input-sha256': source.input_sha256,
        'row-count': source.row_count,
        'expected-first': source.expected_first,
        'expected-last': source.expected_last,
        'expected-digest': source.expected_digest,
        'backend': source.executor_backend,
        'processing-mode': source.processing_mode,
        'source-count': source.source_count,
        'worker-limit': source.worker_limit,
    }
    cmd = ['python', str(child_script), '--child']
    for flag, val in opts.items():
        cmd.extend([f'--{flag}', str(val)])
    if source.path is not None:
        cmd.extend(['--input-path', str(source.path)])
    return cmd


def run_parent_scenario(
    source: ScenarioInput,
    repeats: int,
    root: Path,
    git_sha: str,
    worktree_sha256: str = '',
) -> list[dict[str, Any]]:
    """Run each repeat in isolation with distinct corpus output paths."""
    records: list[dict[str, Any]] = []

    def _fail(idx: int, err: str) -> dict[str, Any]:
        record = unmeasured_record(
            source, idx, status='failed', reason=err, git_sha=git_sha
        )
        record['worktree_sha256'] = worktree_sha256
        return record

    for repeat_index in range(repeats):
        (result_dir := root / f'{source.scenario}-{repeat_index}').mkdir()
        result_path = result_dir / 'result.json'
        command = child_command(source, repeat_index, result_path)
        try:
            proc = run_process(command, cwd=Path.cwd(), check=False)
            if not result_path.is_file():
                reason = proc.stderr.strip() or proc.stdout.strip()
                records.append(_fail(repeat_index, reason))
                continue
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            payload['git_sha'] = git_sha
            payload['worktree_sha256'] = worktree_sha256
            if proc.returncode != 0:
                payload['status'] = 'failed'
                payload['reason'] = (
                    proc.stderr.strip() or 'benchmark child non-zero exit'
                )
            records.append(payload)
        except (ProcessRunnerError, OSError, json.JSONDecodeError) as err:
            records.append(_fail(repeat_index, f'{type(err).__name__}: {err}'))
    return records


def median_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize successful repeats without hiding failed measurements."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.get('status') == 'passed':
            grouped.setdefault(str(r['scenario']), []).append(r)

    def _m(recs: list[dict[str, Any]], k: str) -> float:
        values = (r.get(k, r.get('rss_peak_mib', 0.0)) for r in recs)
        return float(median(values))

    return [
        {
            'scenario': sc,
            'successful_repeats': len(recs),
            'elapsed_seconds_median': _m(recs, 'elapsed_seconds'),
            'rss_peak_mib_median': _m(recs, 'rss_peak_mib'),
            'parent_rss_peak_mib_median': _m(recs, 'parent_rss_peak_mib'),
            'aggregate_rss_peak_mib_median': _m(
                recs, 'aggregate_rss_peak_mib'
            ),
            'output_bytes_median': _m(recs, 'output_bytes'),
        }
        for sc, recs in sorted(grouped.items())
    ]
