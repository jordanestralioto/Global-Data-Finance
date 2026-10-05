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
    REPORT_SCHEMA_VERSION,
    ReportFormatError,
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
            result = _run_isolated_case(
                report_path, case, timeout, progress=True
            )
        else:
            result = _run_isolated_case(report_path, case, timeout)
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
    summary['processCheck'] = _process_check()
    write_json(report_path / 'summary.json', summary)
    output = {'report': str(report_path), **summary}
    sys.stdout.write(
        json.dumps(output, ensure_ascii=True, sort_keys=True) + '\n'
    )
    return _campaign_exit_code(summary)


def _process_check() -> dict[str, Any]:
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


def _run_isolated_case(
    report_path: Path,
    case: ValidationCase,
    timeout: float,
    *,
    progress: bool = False,
) -> dict[str, Any]:
    workspace_parent = _workspace_parent(report_path, case)
    workspace_parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(
        tempfile.mkdtemp(prefix=f'{case.case_id}-', dir=str(workspace_parent))
    )
    log_path = report_path / 'logs' / f'{case.case_id}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context('spawn')
    result_queue: multiprocessing.Queue[dict[str, Any]] = context.Queue()
    process = context.Process(
        target=_case_worker,
        args=(case, timeout, workspace, log_path, result_queue),
    )
    process.start()
    deadline = time.monotonic() + timeout
    result = _receive_worker_result(
        result_queue,
        process,
        deadline,
        progress=progress,
        case_id=case.case_id,
    )
    process.join(timeout=max(0.0, deadline - time.monotonic()))
    if process.is_alive():
        _terminate_process(process)
        result = _control_result(
            case,
            'external_failure',
            f'case exceeded the {timeout:g}s process timeout',
        )
        _append_log(log_path, result['message'])
    elif result is None:
        result = _control_result(
            case,
            'failed',
            'isolated case exited without evidence '
            f'(exit code {process.exitcode})',
        )
    result['temporaryFilesAfterCleanup'] = _cleanup_workspace(
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


def _receive_worker_result(
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


def _terminate_process(process: _TerminableProcess) -> None:
    """Bound process cleanup after a case exceeds its execution timeout."""
    process.terminate()
    process.join(timeout=1.0)
    if not process.is_alive():
        return
    process.kill()
    process.join(timeout=1.0)


def _case_worker(
    case: ValidationCase,
    timeout: float,
    workspace: Path,
    log_path: Path,
    result_queue: multiprocessing.Queue[dict[str, Any]],
) -> None:
    result_queue.put(
        execute_case(
            case,
            timeout=timeout,
            workspace=workspace,
            log_path=log_path,
        )
    )


def _workspace_parent(report_path: Path, case: ValidationCase) -> Path:
    if case.source == 'cvm':
        return Path(case.output_root).expanduser().resolve()
    return report_path / 'work'


def _cleanup_workspace(workspace: Path, log_path: Path) -> list[str]:
    leftovers = temporary_paths(workspace)
    try:
        shutil.rmtree(workspace)
    except OSError as error:
        _append_log(log_path, f'workspace cleanup failed: {error}')
        return leftovers
    return temporary_paths(workspace)


def _control_result(
    case: ValidationCase, status: CaseStatus, message: str
) -> dict[str, Any]:
    return {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'caseId': case.case_id,
        'source': case.source,
        'document': case.document,
        'year': case.year,
        'inputPath': case.input_path,
        'inputSizeBytes': case.input_size_bytes,
        'inputSha256': case.input_sha256,
        'command': case.command(),
        'published': None,
        'publicResult': None,
        'artifactCount': 0,
        'artifacts': [],
        'recordCount': 0,
        'schema': {},
        'temporaryFiles': [],
        'temporaryFilesAfterCleanup': [],
        'status': status,
        'message': message,
        'durationSeconds': 0.0,
    }


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(message + '\n')


def _campaign_exit_code(summary: dict[str, Any]) -> int:
    if summary['processCheck']['status'] != 'passed':
        return 2
    if summary['totalNotExecuted'] > 0:
        return 2
    if summary['totalFunctionalFailures'] > 0:
        return 1
    if summary['totalExternalFailures'] > 0:
        return 2
    return 0
