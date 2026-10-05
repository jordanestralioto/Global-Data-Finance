"""Fresh-process execution and aggregation for benchmark runs."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path
from statistics import median
from typing import Any

import scripts.benchmark_runtime.operations as operations
from scripts.benchmark_runtime.operations import (
    _OPERATIONAL_ERRORS,
    ChildOperation,
    execute_child_operation,
)
from scripts.benchmark_support.digests import sha256_file, verify_input_digest
from scripts.benchmark_support.models import ScenarioInput
from scripts.benchmark_support.monitoring import RssSampler
from scripts.benchmark_support.records import base_record, unmeasured_record
from scripts.benchmark_support.serialization import write_json
from scripts.process_runner import ProcessRunnerError, run_process


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
        phase_seconds.update(operations._last_b3_phase_timings)
        b3_t = operations._last_b3_phase_timings
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
    child_script = (
        Path(__file__).resolve().parent.parent / 'benchmark_ingestion.py'
    )
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
