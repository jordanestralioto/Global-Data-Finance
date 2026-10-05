"""Stable benchmark result record construction."""

from __future__ import annotations

import os
import platform
from datetime import UTC, datetime
from typing import Any

import scripts.benchmark_support.monitoring as monitoring

from .models import SCHEMA_VERSION, ScenarioInput
from .monitoring import MEBIBYTE


def base_record(source: ScenarioInput, repeat_index: int) -> dict[str, Any]:
    """Build fields shared by successful and failed measurements."""
    return {
        'schema_version': SCHEMA_VERSION,
        'git_sha': os.environ.get('GDF_BENCHMARK_GIT_SHA', 'unknown'),
        'worktree_sha256': '',
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count() or 1,
        'available_memory_mib': int(
            monitoring.psutil.virtual_memory().available // MEBIBYTE
        ),
        'timestamp': datetime.now(UTC).isoformat(),
        'scenario': source.scenario,
        'repeat_index': repeat_index,
        'input_sha256': source.input_sha256,
        'row_count': source.row_count,
        'processing_mode': source.processing_mode,
        'executor_backend': source.executor_backend,
        'requested_backend': source.executor_backend,
        'effective_backend': source.executor_backend,
        'source_count': source.source_count,
        'requested_source_count': source.source_count,
        'effective_source_count': source.source_count,
        'worker_limit': source.worker_limit,
        'requested_worker_limit': source.worker_limit,
        'effective_worker_limit': source.worker_limit,
    }


def unmeasured_record(
    source: ScenarioInput,
    repeat_index: int,
    *,
    status: str,
    reason: str,
    git_sha: str | None = None,
    elapsed_seconds: float = 0.0,
    rss_before_mib: float = 0.0,
    rss_peak_mib: float = 0.0,
    rss_after_mib: float = 0.0,
    parent_rss_before_mib: float | None = None,
    parent_rss_peak_mib: float | None = None,
    parent_rss_after_mib: float | None = None,
    aggregate_rss_peak_mib: float | None = None,
    child_process_count_peak: int = 0,
    worker_pids_observed: list[int] | None = None,
) -> dict[str, Any]:
    """Build a failed or skipped benchmark record with stable empty metrics."""
    record = base_record(source, repeat_index)
    if git_sha is not None:
        record['git_sha'] = git_sha
    phase_seconds = (
        {'operation': elapsed_seconds} if elapsed_seconds > 0.0 else {}
    )

    def _v(val: float | None, alt_val: float) -> float:
        return alt_val if val is None else val

    p_b = _v(parent_rss_before_mib, rss_before_mib)
    p_p = _v(parent_rss_peak_mib, rss_peak_mib)
    p_a = _v(parent_rss_after_mib, rss_after_mib)
    agg = _v(aggregate_rss_peak_mib, rss_peak_mib)
    record.update(
        {
            'schema_fingerprint': '',
            'logical_digest': '',
            'artifact_sha256': '',
            'logical_equivalence': False,
            'elapsed_seconds': elapsed_seconds,
            'phase_seconds': phase_seconds,
            'rss_before_mib': rss_before_mib,
            'rss_peak_mib': rss_peak_mib,
            'rss_after_mib': rss_after_mib,
            'parent_rss_before_mib': p_b,
            'parent_rss_peak_mib': p_p,
            'parent_rss_after_mib': p_a,
            'aggregate_rss_peak_mib': agg,
            'child_process_count_peak': child_process_count_peak,
            'worker_pids_observed': (
                [] if worker_pids_observed is None else worker_pids_observed
            ),
            'output_bytes': 0,
            'status': status,
            'reason': reason,
        }
    )
    return record
