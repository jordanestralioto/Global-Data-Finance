"""Deterministic tests for case dispatch and status classification."""

from __future__ import annotations

import sys
from os import sep
from pathlib import Path
from typing import Any, cast

import pytest

import scripts.real_validation_cases as case_module
import scripts.real_validation_runner as runner
from scripts.real_validation_types import (
    ExternalFailure,
    NotPublished,
    ValidationCase,
)

pytestmark = pytest.mark.unit


def _case(source: str = 'cotahist') -> ValidationCase:
    """Build one dispatch case for the selected public source."""
    if source == 'cotahist':
        return ValidationCase(
            case_id='cotahist-fast-2024',
            source='cotahist',
            year=2024,
            input_path=str(Path(sep, 'tmp', 'COTAHIST_A2024.ZIP')),
            output_root='',
            mode='fast',
        )
    return ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path='https://example.test/dfp.zip',
        output_root=str(Path(sep, 'tmp', 'cvm-output')),
        document='DFP',
        mode='cvm',
        url='https://example.test/dfp.zip',
    )


def test_execute_case_dispatches_b3_and_records_worker_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B3 dispatch retains stdout and temporary-file evidence."""
    case = _case()

    def fake_b3(
        _current: ValidationCase, workspace: Path
    ) -> dict[str, object]:
        sys.stdout.write('controlled worker output\n')
        (workspace / 'artifact.tmp').touch()
        return {'status': 'passed', 'message': 'ok'}

    monkeypatch.setattr(case_module, 'execute_cotahist_case', fake_b3)
    log_path = tmp_path / 'logs' / 'case.log'
    log_path.parent.mkdir()

    result = case_module.execute_case(
        case,
        timeout=2.0,
        workspace=tmp_path / 'workspace',
        log_path=log_path,
    )

    assert result['status'] == 'passed'
    assert result['temporaryFiles'] == ['artifact.tmp']
    assert 'controlled worker output' in log_path.read_text(encoding='utf-8')


def test_execute_case_dispatches_cvm_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CVM dispatch forwards the per-case timeout to its validator."""
    case = _case('cvm')
    calls: list[float] = []

    def fake_cvm(
        _current: ValidationCase, _workspace: Path, timeout: float
    ) -> dict[str, object]:
        calls.append(timeout)
        return {'status': 'passed', 'message': 'ok'}

    monkeypatch.setattr(case_module, 'execute_cvm_case', fake_cvm)

    result = case_module.execute_case(
        case,
        timeout=3.5,
        workspace=tmp_path / 'workspace',
        log_path=tmp_path / 'case.log',
    )

    assert result['status'] == 'passed'
    assert calls == [3.5]


@pytest.mark.parametrize(
    ('raised', 'expected_status'),
    [
        (NotPublished('not published'), 'not_published'),
        (ExternalFailure('network unavailable'), 'external_failure'),
        (ValueError('invalid artifact'), 'failed'),
    ],
)
def test_execute_case_classifies_boundary_and_functional_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
    expected_status: str,
) -> None:
    """Boundary statuses stay distinct from ordinary functional failures."""
    case = _case()

    def raising_b3(
        _current: ValidationCase, _workspace: Path
    ) -> dict[str, object]:
        raise raised

    monkeypatch.setattr(case_module, 'execute_cotahist_case', raising_b3)
    log_path = tmp_path / 'logs' / f'{expected_status}.log'
    log_path.parent.mkdir()

    result = case_module.execute_case(
        case,
        timeout=2.0,
        workspace=tmp_path / expected_status,
        log_path=log_path,
    )

    assert result['status'] == expected_status
    assert str(raised) in result['message']
    assert result['durationSeconds'] >= 0
    if expected_status == 'failed':
        assert 'ValueError' in log_path.read_text(encoding='utf-8')


def test_case_worker_puts_execute_result_on_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spawn target forwards exactly one complete result to its queue."""
    case = _case()
    expected: dict[str, object] = {
        'caseId': case.case_id,
        'status': 'passed',
    }
    values: list[dict[str, object]] = []

    def fake_execute(
        current: ValidationCase,
        *,
        timeout: float,
        workspace: Path,
        log_path: Path,
    ) -> dict[str, object]:
        assert current == case
        assert timeout == 2.0
        assert workspace == tmp_path / 'workspace'
        assert log_path == tmp_path / 'case.log'
        return expected

    class Queue:
        def put(self, value: dict[str, object]) -> None:
            values.append(value)

    monkeypatch.setattr(runner, 'execute_case', fake_execute)

    runner.case_worker(
        case,
        2.0,
        tmp_path / 'workspace',
        tmp_path / 'case.log',
        cast(Any, Queue()),
    )

    assert values == [expected]
