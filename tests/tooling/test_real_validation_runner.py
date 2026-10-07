"""Deterministic tests for campaign lifecycle and process isolation."""

from __future__ import annotations

import json
import queue as queue_module
from dataclasses import replace
from functools import partial
from os import sep
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import scripts.real_validation_runner as runner
from scripts import real_validation as cli
from scripts.real_validation_report import (
    ReportFormatError,
    read_json,
    write_json,
    write_results,
)
from scripts.real_validation_types import (
    CaseStatus,
    ValidationCase,
    ValidationInputSnapshot,
)
from scripts.real_validation_utils import sha256_file
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.unit


def _cvm_case(
    case_id: str, output_root: str = str(Path(sep, 'tmp', 'output'))
) -> ValidationCase:
    """Build a lightweight CVM case for runner lifecycle tests."""
    return ValidationCase(
        case_id=case_id,
        source='cvm',
        year=2024,
        input_path=f'https://example.test/{case_id}.zip',
        output_root=output_root,
        document='DFP',
        mode='cvm',
        url=f'https://example.test/{case_id}.zip',
    )


def test_cli_progress_preserves_machine_readable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Opt-in progress stays on stderr while stdout remains one JSON result."""
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    write_cotahist_zip(inputs, year=2024, records=[build_cotahist_record()])

    def complete_case(report, case, timeout, *, progress):
        assert report == tmp_path / 'report'
        assert timeout == 60.0
        assert progress is True
        return runner.control_result(case, 'passed', 'controlled completion')

    monkeypatch.setattr(runner, 'run_isolated_case', complete_case)
    code = cli.main(
        [
            '--source',
            'cotahist',
            '--cotahist-path',
            str(inputs),
            '--initial-year',
            '2024',
            '--last-year',
            '2024',
            '--cotahist-mode',
            'fast',
            '--report',
            str(tmp_path / 'report'),
            '--progress',
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out)['totalApproved'] == 1
    assert 'Preparing campaign inputs' in captured.err
    assert 'cotahist-fast-2024: started' in captured.err
    assert 'cotahist-fast-2024: passed' in captured.err


def test_wait_progress_keeps_the_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An active worker reports elapsed time without extending its deadline."""
    ticks = iter([0.0, 0.0, 31.0, 31.0])
    monkeypatch.setattr(
        runner, 'time', SimpleNamespace(monotonic=lambda: next(ticks))
    )
    result = {'status': 'passed'}
    waits = []

    class ResultQueue:
        def get(self, *, timeout):
            waits.append(timeout)
            if len(waits) == 1:
                raise queue_module.Empty
            return result

    observed = runner.receive_worker_result(
        cast(Any, ResultQueue()),
        _StubbornProcess(),
        100.0,
        progress=True,
        case_id='cotahist-fast-2024',
    )
    captured = capsys.readouterr()

    assert observed == result
    assert waits == [1.0, 1.0]
    assert captured.out == ''
    assert 'cotahist-fast-2024: worker active; elapsed=31s' in captured.err


def test_run_campaign_skips_terminal_results_and_persists_pending_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal cases remain stable while pending work is persisted."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    terminal = [
        _cvm_case('case-failed'),
        _cvm_case('case-not-published'),
        _cvm_case('case-passed'),
        _cvm_case('case-skipped'),
    ]
    pending = _cvm_case('case-pending')
    cases = [*terminal, pending]
    statuses = {
        'case-failed': 'failed',
        'case-not-published': 'not_published',
        'case-passed': 'passed',
        'case-skipped': 'skipped',
    }
    write_results(
        report_path / 'results.jsonl',
        {
            case_id: {
                'caseId': case_id,
                'status': status,
                'published': status == 'passed',
            }
            for case_id, status in statuses.items()
        },
    )
    called: list[str] = []

    def fake_run(
        _report: Path, case: ValidationCase, _timeout: float
    ) -> dict[str, object]:
        called.append(case.case_id)
        return runner.control_result(case, 'passed', 'done')

    monkeypatch.setattr(runner, 'run_isolated_case', fake_run)

    exit_code = runner.run_campaign(report_path, cases, timeout=2.0)
    summary = read_json(report_path / 'summary.json')

    assert exit_code == 1
    assert called == ['case-pending']
    assert summary['totalCombinations'] == 5
    assert summary['totalApproved'] == 2
    assert summary['totalExecuted'] == 5
    assert summary['processCheck']['status'] == 'passed'


@pytest.mark.parametrize(
    ('status', 'expected_code'),
    [('failed', 1), ('external_failure', 2), ('skipped', 0)],
)
def test_run_campaign_maps_new_case_status_to_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: CaseStatus,
    expected_code: int,
) -> None:
    """Functional and external outcomes have distinct campaign exit codes."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    case = _cvm_case('case-new')

    def fake_run(
        _report: Path, current: ValidationCase, _timeout: float
    ) -> dict[str, object]:
        return runner.control_result(current, status, status)

    monkeypatch.setattr(runner, 'run_isolated_case', fake_run)

    assert (
        runner.run_campaign(report_path, [case], timeout=2.0) == expected_code
    )


def test_run_campaign_rejects_unexpected_and_invalid_result_lines(
    tmp_path: Path,
) -> None:
    """Result evidence outside the manifest or with an unknown status fails."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    case = _cvm_case('case-one')
    write_results(
        report_path / 'results.jsonl',
        {'stale': {'caseId': 'stale', 'status': 'passed'}},
    )
    with pytest.raises(ReportFormatError, match='outside the manifest'):
        runner.run_campaign(report_path, [case], timeout=2.0)

    write_results(
        report_path / 'results.jsonl',
        {'case-one': {'caseId': 'case-one', 'status': 'unknown'}},
    )
    with pytest.raises(ReportFormatError, match='invalid campaign status'):
        runner.run_campaign(report_path, [case], timeout=2.0)


def test_campaign_exit_code_is_fail_closed_for_process_and_incomplete_states():
    """Process failures and unexecuted cases take precedence over outcomes."""
    base = {
        'processCheck': {'status': 'passed'},
        'totalNotExecuted': 0,
        'totalFunctionalFailures': 0,
        'totalExternalFailures': 0,
    }

    assert (
        runner.campaign_exit_code(
            {**base, 'processCheck': {'status': 'failed'}}
        )
        == 2
    )
    assert runner.campaign_exit_code({**base, 'totalNotExecuted': 1}) == 2
    assert (
        runner.campaign_exit_code({**base, 'totalFunctionalFailures': 1}) == 1
    )
    assert runner.campaign_exit_code({**base, 'totalExternalFailures': 1}) == 2
    assert runner.campaign_exit_code(base) == 0


def test_process_check_reports_active_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner exposes an active child instead of silently passing."""

    class ActiveChild:
        pid = 42
        name = 'validation-child'
        exitcode = None

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(
        runner.multiprocessing,
        'active_children',
        lambda: [ActiveChild()],
    )

    check = runner.process_check()

    assert check == {
        'status': 'failed',
        'activeProcesses': [
            {'pid': 42, 'name': 'validation-child', 'exitcode': None}
        ],
    }


def test_workspace_parent_selects_caller_output_only_for_cvm(
    tmp_path: Path,
) -> None:
    """CVM workspaces stay under the validated caller output root."""
    cvm_case = _cvm_case('cvm-case', str(tmp_path / 'cvm'))
    b3_case = ValidationCase(
        case_id='cotahist-fast-2024',
        source='cotahist',
        year=2024,
        input_path=str(Path(sep, 'tmp', 'COTAHIST_A2024.ZIP')),
        output_root='',
        mode='fast',
    )

    assert (
        runner.workspace_parent(tmp_path / 'report', cvm_case)
        == (tmp_path / 'cvm').resolve()
    )
    assert runner.workspace_parent(tmp_path / 'report', b3_case) == (
        tmp_path / 'report' / 'work'
    )


class _FakeQueue:
    """Queue replacement for parent-side process lifecycle tests."""

    def __init__(self, result: dict[str, object] | None, empty: bool) -> None:
        self.result = result
        self.empty = empty
        self.closed = False

    def get(self, *, timeout: float) -> dict[str, object]:
        assert 0 < timeout <= 1.0
        if self.empty:
            raise queue_module.Empty
        assert self.result is not None
        return self.result

    def close(self) -> None:
        self.closed = True

    def join_thread(self) -> None:
        return None


class _FakeProcess:
    """Controllable process replacement used to exercise parent branches."""

    pid = 99
    exitcode = 0

    def __init__(self, alive: bool) -> None:
        self.alive = alive
        self.terminated = False

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        return None

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False


class _StubbornProcess:
    """Process double that requires bounded termination followed by kill."""

    def __init__(self) -> None:
        self.alive = True
        self.terminated = False
        self.killed = False
        self.join_timeouts: list[float | None] = []

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive


class _FakeContext:
    """Context replacement that binds queue and process per scenario."""

    def __init__(
        self,
        result_queue: _FakeQueue,
        process: _FakeProcess,
        case: ValidationCase,
    ) -> None:
        self.result_queue = result_queue
        self.process = process
        self.case = case

    def Queue(self) -> _FakeQueue:
        return self.result_queue

    def Process(
        self, target: object, args: tuple[object, ...]
    ) -> _FakeProcess:
        assert target is runner.case_worker
        assert args[0] == self.case
        return self.process


def _create_fake_workspace(
    path: Path, *_args: object, **_kwargs: object
) -> str:
    """Create the controlled workspace expected by ``mkdtemp``."""
    path.mkdir(parents=True)
    return str(path)


def test_run_isolated_case_handles_result_timeout_and_missing_worker_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner classifies normal, timeout, and empty-worker branches."""
    for label, alive, empty, expected_status in (
        ('result', False, False, 'passed'),
        ('timeout', True, False, 'external_failure'),
        ('empty', False, True, 'failed'),
    ):
        report_path = tmp_path / label / 'report'
        report_path.mkdir(parents=True)
        output_root = tmp_path / label / 'output'
        case = _cvm_case(label, str(output_root))
        queue = _FakeQueue(
            runner.control_result(case, 'passed', 'worker result'), empty
        )
        process = _FakeProcess(alive)
        workspace = output_root / 'known-workspace'

        monkeypatch.setattr(
            runner.tempfile,
            'mkdtemp',
            partial(_create_fake_workspace, workspace),
        )
        monkeypatch.setattr(
            runner.multiprocessing,
            'get_context',
            lambda _method, _queue=queue, _process=process, _case=case: (
                _FakeContext(_queue, _process, _case)
            ),
        )

        result = runner.run_isolated_case(report_path, case, timeout=0.1)

        assert result['status'] == expected_status
        assert result['temporaryFilesAfterCleanup'] == []
        assert result['logPath'] == f'logs/{case.case_id}.log'
        assert not workspace.exists()
        if alive:
            assert process.terminated is True


def test_terminate_process_never_uses_an_unbounded_join() -> None:
    """A stuck timeout cleanup escalates to kill with finite grace periods."""
    process = _StubbornProcess()

    runner.terminate_process(process)

    assert process.terminated is True
    assert process.killed is True
    assert process.join_timeouts == [1.0, 1.0]


def test_cleanup_workspace_preserves_leftovers_when_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup failures are logged and leave inspectable paths in evidence."""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'staging.tmp').touch()
    log_path = tmp_path / 'logs' / 'case.log'

    def fail_rmtree(_path: Path) -> None:
        raise OSError('permission denied')

    monkeypatch.setattr(runner.shutil, 'rmtree', fail_rmtree)

    leftovers = runner.cleanup_workspace(workspace, log_path)

    assert leftovers == ['staging.tmp']
    assert 'workspace cleanup failed' in log_path.read_text(encoding='utf-8')


def test_resume_rejects_manifest_without_hash_metadata(
    tmp_path: Path,
) -> None:
    """A legacy or tampered manifest cannot resume without input evidence."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    case = ValidationCase(
        case_id='cotahist-fast-2024',
        source='cotahist',
        year=2024,
        input_path=str(archive),
        output_root='',
        mode='fast',
    )
    report_path = tmp_path / 'report'
    report_path.mkdir()
    write_json(
        report_path / 'manifest.json',
        {'schemaVersion': 2, 'cases': [case.to_manifest_dict()]},
    )

    with pytest.raises(ReportFormatError, match='manifest_metadata'):
        runner.resume_cases(report_path)


def test_resume_rejects_inputs_from_multiple_directories(
    tmp_path: Path,
) -> None:
    """A single COTAHIST campaign cannot mix independent input roots."""
    first_dir = tmp_path / 'first'
    second_dir = tmp_path / 'second'
    first_dir.mkdir()
    second_dir.mkdir()
    first = write_cotahist_zip(
        first_dir,
        year=2023,
        records=[build_cotahist_record(year=2023)],
    )
    second = write_cotahist_zip(
        second_dir,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    cases = [
        ValidationCase(
            case_id='cotahist-fast-2023',
            source='cotahist',
            year=2023,
            input_path=str(first),
            output_root='',
            mode='fast',
            input_size_bytes=first.stat().st_size,
            input_sha256=sha256_file(first),
            input_files=(
                ValidationInputSnapshot(
                    str(first.resolve()),
                    first.stat().st_size,
                    sha256_file(first),
                ),
            ),
        ),
        ValidationCase(
            case_id='cotahist-fast-2024',
            source='cotahist',
            year=2024,
            input_path=str(second),
            output_root='',
            mode='fast',
            input_size_bytes=second.stat().st_size,
            input_sha256=sha256_file(second),
            input_files=(
                ValidationInputSnapshot(
                    str(second.resolve()),
                    second.stat().st_size,
                    sha256_file(second),
                ),
            ),
        ),
    ]
    report_path = tmp_path / 'report'
    report_path.mkdir()
    from scripts.real_validation_report import write_json

    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 2,
            'cases': [case.to_manifest_dict() for case in cases],
        },
    )

    with pytest.raises(ReportFormatError, match='multiple directories'):
        runner.resume_cases(report_path)


def test_resume_rejects_tampered_cvm_url_before_worker_execution(
    tmp_path: Path,
) -> None:
    """A CVM endpoint persisted in a report cannot override the matrix."""
    output_root = str(tmp_path / 'cvm-output')
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        'dfp_cia_aberta_2024.zip'
    )
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=output_root,
        document='DFP',
        mode='cvm',
        url=url,
    )
    tampered = replace(
        case,
        input_path='http://127.0.0.1/private',
        url='http://127.0.0.1/private',
    )
    report_path = tmp_path / 'report'
    report_path.mkdir()
    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 2,
            'campaign': {'cvmOutput': output_root},
            'cases': [tampered.to_manifest_dict()],
        },
    )

    with pytest.raises(ReportFormatError, match='official matrix'):
        runner.resume_cases(report_path)


def test_resume_rejects_cvm_output_root_drift_before_worker_execution(
    tmp_path: Path,
) -> None:
    """A case output cannot escape the campaign destination on resume."""
    trusted_output = tmp_path / 'trusted-output'
    attacker_output = tmp_path / 'attacker-output'
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        'dfp_cia_aberta_2024.zip'
    )
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=str(attacker_output),
        document='DFP',
        mode='cvm',
        url=url,
    )
    report_path = tmp_path / 'report'
    report_path.mkdir()
    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 2,
            'campaign': {'cvmOutput': str(trusted_output)},
            'cases': [case.to_manifest_dict()],
        },
    )

    with pytest.raises(ReportFormatError, match='outputRoot'):
        runner.resume_cases(report_path)

    assert not trusted_output.exists()
    assert not attacker_output.exists()


def test_resume_rejects_cotahist_case_bound_to_a_different_catalog_year(
    tmp_path: Path,
) -> None:
    """The COTAHIST case ID, year, and selected input must agree on resume."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    case = ValidationCase(
        case_id='cotahist-fast-2023',
        source='cotahist',
        year=2024,
        input_path=str(archive),
        output_root='',
        mode='fast',
        input_size_bytes=archive.stat().st_size,
        input_sha256=sha256_file(archive),
        input_files=(
            ValidationInputSnapshot(
                str(archive.resolve()),
                archive.stat().st_size,
                sha256_file(archive),
            ),
        ),
    )
    report_path = tmp_path / 'report'
    report_path.mkdir()
    write_json(
        report_path / 'manifest.json',
        {'schemaVersion': 2, 'cases': [case.to_manifest_dict()]},
    )

    with pytest.raises(ReportFormatError, match='identity'):
        runner.resume_cases(report_path)
