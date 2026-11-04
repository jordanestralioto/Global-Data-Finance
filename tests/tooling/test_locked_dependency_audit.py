"""Status and source checks for the uv-locked dependency audit."""

import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from scripts import audit_locked_dependencies

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('audit_code', 'vulnerabilities', 'expected'),
    [
        (0, [], 0),
        (1, [{'id': 'PYSEC-1'}], 1),
        (1, [], 2),
    ],
)
def test_audit_classifies_complete_reports(
    monkeypatch: pytest.MonkeyPatch,
    audit_code: int,
    vulnerabilities: list[dict[str, str]],
    expected: int,
) -> None:
    commands: list[list[str]] = []

    def fake_run_process(
        command: list[str], **_kwargs: Any
    ) -> CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ['uv', 'export']:
            Path(command[command.index('--output-file') + 1]).write_text(
                'example==1.0\n', encoding='utf-8'
            )
            return CompletedProcess(command, 0, '', '')
        Path(command[command.index('--output') + 1]).write_text(
            json.dumps(
                {
                    'dependencies': [
                        {
                            'name': 'example',
                            'version': '1.0',
                            'vulns': vulnerabilities,
                        }
                    ],
                    'fixes': [],
                }
            ),
            encoding='utf-8',
        )
        return CompletedProcess(command, audit_code, '', '')

    monkeypatch.setattr(
        audit_locked_dependencies, 'run_process', fake_run_process
    )

    assert audit_locked_dependencies.main() == expected
    assert commands[0][:3] == ['uv', 'export', '--locked']
    assert '--offline' in commands[0]
    assert '--dev' in commands[0]
    assert commands[1][:3] == ['python', '-m', 'pip_audit']
    assert '--disable-pip' in commands[1]
    assert '--require-hashes' in commands[1]


def test_audit_reports_external_failure_without_a_complete_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run_process(
        command: list[str], **_kwargs: Any
    ) -> CompletedProcess[str]:
        if command[:2] == ['uv', 'export']:
            Path(command[command.index('--output-file') + 1]).write_text(
                'example==1.0\n', encoding='utf-8'
            )
            return CompletedProcess(command, 0, '', '')
        return CompletedProcess(command, 1, '', 'socket.gaierror: DNS failed')

    monkeypatch.setattr(
        audit_locked_dependencies, 'run_process', fake_run_process
    )

    assert audit_locked_dependencies.main() == 2
    assert 'EXTERNAL_FAILURE' in capsys.readouterr().out


def test_audit_rejects_incomplete_lock_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_locked_dependencies,
        'run_process',
        lambda command, **_kwargs: CompletedProcess(command, 1, '', ''),
    )

    assert audit_locked_dependencies.main() == 2


def test_audit_rejects_malformed_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_process(
        command: list[str], **_kwargs: Any
    ) -> CompletedProcess[str]:
        if command[:2] == ['uv', 'export']:
            Path(command[command.index('--output-file') + 1]).write_text(
                'example==1.0\n', encoding='utf-8'
            )
        else:
            Path(command[command.index('--output') + 1]).write_text(
                'not json', encoding='utf-8'
            )
        return CompletedProcess(command, 0, '', '')

    monkeypatch.setattr(
        audit_locked_dependencies, 'run_process', fake_run_process
    )

    assert audit_locked_dependencies.main() == 2
