"""Tests for the allowlisted command adapter used by quality gates."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

process_runner = import_module('scripts.process_runner')


pytestmark = pytest.mark.unit


def test_resolve_python_uses_the_current_interpreter() -> None:
    """Python resolution must not depend on a mutable PATH entry."""
    assert (
        process_runner.resolve_executable('python')
        == process_runner.sys.executable
    )


def test_resolve_allowlisted_executable_uses_path_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-Python commands must resolve through the operating-system PATH."""
    monkeypatch.setattr(
        process_runner.shutil, 'which', lambda name: f'/bin/{name}'
    )

    assert process_runner.resolve_executable('git') == '/bin/git'


def test_resolve_rejects_executable_outside_the_allowlist() -> None:
    """The adapter must reject commands that are not repository-approved."""
    with pytest.raises(process_runner.UnsupportedExecutableError):
        process_runner.resolve_executable('curl')


def test_run_process_uses_shell_false_and_returns_process_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The adapter must preserve the child result and disable shell parsing."""
    calls: list[dict[str, object]] = []
    expected = SimpleNamespace(returncode=0, stdout='ok', stderr='')

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append({'args': args, **kwargs})
        return expected

    monkeypatch.setattr(process_runner.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(process_runner.subprocess, 'run', fake_run)

    result = process_runner.run_process(
        ['git', 'status'], cwd=tmp_path, check=False
    )

    assert result is expected
    assert calls[0]['shell'] is False
    assert calls[0]['cwd'] == tmp_path
    assert calls[0]['args'] == (['/bin/git', 'status'],)


def test_run_process_propagates_nonzero_return_when_check_is_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Callers that inspect command status must receive the non-zero result."""
    expected = SimpleNamespace(returncode=7, stdout='', stderr='failed')
    monkeypatch.setattr(process_runner.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(
        process_runner.subprocess,
        'run',
        lambda *_args, **_kwargs: expected,
    )

    result = process_runner.run_process(
        ['git', 'show'], cwd=tmp_path, check=False
    )

    assert result.returncode == 7
    assert result.stderr == 'failed'


def test_run_process_translates_command_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failing checked command must expose adapter context and its cause."""
    failure = process_runner.subprocess.CalledProcessError(
        3, ['git', 'status'], stderr='failed'
    )
    monkeypatch.setattr(process_runner.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(
        process_runner.subprocess,
        'run',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(process_runner.ProcessRunnerError, match='exit code 3'):
        process_runner.run_process(['git', 'status'], cwd=tmp_path)


def test_run_process_passes_custom_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The adapter must pass custom environment variables to subprocess."""
    received_env: object = None
    expected = SimpleNamespace(returncode=0, stdout='ok', stderr='')

    def fake_run(*_args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal received_env
        received_env = kwargs.get('env')
        return expected

    monkeypatch.setattr(process_runner.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(process_runner.subprocess, 'run', fake_run)

    process_runner.run_process(
        ['git', 'status'],
        cwd=tmp_path,
        env={'CUSTOM_VAR': '1'},
        check=False,
    )

    assert received_env == {'CUSTOM_VAR': '1'}
