"""Process-isolated execution and lifecycle for real-validation cases."""

from __future__ import annotations

import json
import multiprocessing
import queue
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol, cast

from .real_validation_cases import execute_case
from .real_validation_report import (
    ReportFormatError,
    build_case_result,
    build_summary,
    read_results,
    validate_status,
    write_json,
    write_results,
)
from .real_validation_resume import resume_cases as _resume_cases
from .real_validation_types import CaseStatus, ValidationCase
from .real_validation_utils import (
    emit_progress,
    sha256_file,
    temporary_paths,
)


class _TerminableProcess(Protocol):
    """The finite process lifecycle required by timeout cleanup."""

    def is_alive(self) -> bool:
        """Return whether the child still owns execution resources."""

    def join(self, timeout: float | None = None) -> None:
        """Wait for at most the supplied finite interval."""

    def terminate(self) -> None:
        """Request graceful process termination."""

    def kill(self) -> None:
        """Force termination after the grace interval expires."""


def resume_cases(report_path: Path) -> list[ValidationCase]:
    """Read and validate a manifest before resuming execution."""
    return _resume_cases(report_path, hash_file=sha256_file)


def run_campaign(
    report_path: Path,
    cases: list[ValidationCase],
    timeout: float,
    *,
    progress: bool = False,
) -> int:
    """Run pending cases, persist every result, and emit a summary."""
    results_path = report_path / 'results.jsonl'
    results = read_results(results_path)
    expected_case_ids = [case.case_id for case in cases]
    expected = set(expected_case_ids)
    unexpected = sorted(set(results) - expected)
    if unexpected:
        raise ReportFormatError(
            f'results contain cases outside the manifest: {unexpected}'
        )
    for result in results.values():
        validate_status(result.get('status'))
    start_time = time.perf_counter()
    for index, case in enumerate(cases, start=1):
        previous = results.get(case.case_id)
        if previous is not None and validate_status(
            previous.get('status')
        ) in {
            'passed',
            'failed',
            'skipped',
            'not_published',
        }:
            if progress:
                emit_progress(
                    f'[{index}/{len(cases)}] {case.case_id}: '
                    f'retained {previous["status"]}'
                )
            continue
        if progress:
            emit_progress(f'[{index}/{len(cases)}] {case.case_id}: started')
            result = run_isolated_case(
                report_path, case, timeout, progress=True
            )
        else:
            result = run_isolated_case(report_path, case, timeout)
        validate_status(result.get('status'))
        results[case.case_id] = result
        write_results(results_path, results)
        if progress:
            emit_progress(f'{case.case_id}: {result["status"]}')
    summary = build_summary(
        expected_case_ids,
        results,
        time.perf_counter() - start_time,
    )
    summary['processCheck'] = process_check()
    write_json(report_path / 'summary.json', summary)
    output = {'report': str(report_path), **summary}
    sys.stdout.write(
        json.dumps(output, ensure_ascii=True, sort_keys=True) + '\n'
    )
    return campaign_exit_code(summary)


def process_check() -> dict[str, Any]:
    """Confirm that no isolated case process remains alive."""
    active = [
        {
            'pid': process.pid,
            'name': process.name,
            'exitcode': process.exitcode,
        }
        for process in multiprocessing.active_children()
        if process.is_alive()
    ]
    return {
        'status': 'passed' if not active else 'failed',
        'activeProcesses': active,
    }


def run_isolated_case(
    report_path: Path,
    case: ValidationCase,
    timeout: float,
    *,
    progress: bool = False,
) -> dict[str, Any]:
    """Execute a case in a spawned process with bounded cleanup."""
    parent_directory = workspace_parent(report_path, case)
    parent_directory.mkdir(parents=True, exist_ok=True)
    workspace = Path(
        tempfile.mkdtemp(prefix=f'{case.case_id}-', dir=str(parent_directory))
    )
    log_path = report_path / 'logs' / f'{case.case_id}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context('spawn')
    result_queue: multiprocessing.Queue[dict[str, Any]] = context.Queue()
    process = context.Process(
        target=case_worker,
        args=(case, timeout, workspace, log_path, result_queue),
    )
    process.start()
    deadline = time.monotonic() + timeout
    result = receive_worker_result(
        result_queue,
        process,
        deadline,
        progress=progress,
        case_id=case.case_id,
    )
    process.join(timeout=max(0.0, deadline - time.monotonic()))
    if process.is_alive():
        terminate_process(process)
        result = control_result(
            case,
            'external_failure',
            f'case exceeded the {timeout:g}s process timeout',
        )
        _append_log(log_path, result['message'])
    elif result is None:
        result = control_result(
            case,
            'failed',
            'isolated case exited without evidence '
            f'(exit code {process.exitcode})',
        )
    result['temporaryFilesAfterCleanup'] = cleanup_workspace(
        workspace, log_path
    )
    result['temporaryFiles'] = sorted(
        set(result.get('temporaryFiles', [])) | set(temporary_paths(workspace))
    )
    result['caseId'] = case.case_id
    result['status'] = cast(CaseStatus, result.get('status', 'failed'))
    result['logPath'] = str(log_path.relative_to(report_path))
    result_queue.close()
    result_queue.join_thread()
    return result


def receive_worker_result(
    result_queue: multiprocessing.Queue[dict[str, Any]],
    process: _TerminableProcess,
    deadline: float,
    *,
    progress: bool = False,
    case_id: str = '',
) -> dict[str, Any] | None:
    """Drain evidence before joining the child that flushes the queue."""
    started = time.monotonic()
    next_progress = started + 30.0
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            return result_queue.get(timeout=min(1.0, remaining))
        except queue.Empty:
            if not process.is_alive():
                return None
            if progress:
                now = time.monotonic()
                if now >= next_progress:
                    emit_progress(
                        f'{case_id}: worker active; '
                        f'elapsed={now - started:.0f}s'
                    )
                    next_progress = now + 30.0
    return None


def terminate_process(process: _TerminableProcess) -> None:
    """Bound process cleanup after a case exceeds its execution timeout."""
    process.terminate()
    process.join(timeout=1.0)
    if not process.is_alive():
        return
    process.kill()
    process.join(timeout=1.0)


def case_worker(
    case: ValidationCase,
    timeout: float,
    workspace: Path,
    log_path: Path,
    result_queue: multiprocessing.Queue[dict[str, Any]],
) -> None:
    """Execute one validation case and send its evidence to the parent."""
    result_queue.put(
        execute_case(
            case,
            timeout=timeout,
            workspace=workspace,
            log_path=log_path,
        )
    )


def workspace_parent(report_path: Path, case: ValidationCase) -> Path:
    """Select the caller-owned CVM output or campaign work directory."""
    if case.source == 'cvm':
        return Path(case.output_root).expanduser().resolve()
    return report_path / 'work'


def cleanup_workspace(workspace: Path, log_path: Path) -> list[str]:
    """Remove case artifacts and report any remaining temporary paths."""
    leftovers = temporary_paths(workspace)
    try:
        shutil.rmtree(workspace)
    except OSError as error:
        _append_log(log_path, f'workspace cleanup failed: {error}')
        return leftovers
    return temporary_paths(workspace)


def control_result(
    case: ValidationCase, status: CaseStatus, message: str
) -> dict[str, Any]:
    """Build a complete report record for a process control outcome."""
    return build_case_result(case, status=status, message=message)


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(message + '\n')


def campaign_exit_code(summary: dict[str, Any]) -> int:
    """Map campaign failures and missing evidence to the CLI exit code."""
    if summary['processCheck']['status'] != 'passed':
        return 2
    if summary['totalNotExecuted'] > 0:
        return 2
    if summary['totalFunctionalFailures'] > 0:
        return 1
    if summary['totalExternalFailures'] > 0:
        return 2
    return 0
