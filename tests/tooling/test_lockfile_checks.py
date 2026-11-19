"""Classification of the native uv lockfile coherence check."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from scripts import check_lockfile_sync, lockfile_checks
from scripts.diagnostics import DIAGNOSTIC_LIMIT
from tests.support.git_repository import initialize_git_repository, run_git

pytestmark = pytest.mark.unit


def _uv_exiting(
    returncode: int, stderr: str = ''
) -> Callable[..., CompletedProcess[str]]:
    """Return a process runner that simulates one uv exit status."""

    def fake_run_process(
        command: list[str], **_kwargs: Any
    ) -> CompletedProcess[str]:
        return CompletedProcess(command, returncode, '', stderr)

    return fake_run_process


def _check(root: Path) -> bool:
    """Ask the native check about the root manifest and its uv.lock."""
    return lockfile_checks.is_lockfile_in_sync(
        Path('pyproject.toml'), Path(), ['uv.lock'], root
    )


@pytest.mark.parametrize(('returncode', 'expected'), [(0, True), (1, False)])
def test_uv_status_separates_coherence_from_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    expected: bool,
) -> None:
    """Exit 1 is uv's deterministic "needs to be updated" outcome."""
    monkeypatch.setattr(
        lockfile_checks, 'run_process', _uv_exiting(returncode)
    )

    assert _check(tmp_path) is expected


def test_other_uv_statuses_are_infrastructure_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A resolver or network failure keeps its diagnostic cause."""
    monkeypatch.setattr(
        lockfile_checks,
        'run_process',
        _uv_exiting(2, 'error: Failed to fetch: https://pypi.org/simple/x/'),
    )

    with pytest.raises(
        lockfile_checks.LockfileInfrastructureError, match='Failed to fetch'
    ):
        _check(tmp_path)


def test_gate_reports_an_error_when_uv_cannot_decide(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An undecided check is ERROR, never a lockfile accusation."""
    initialize_git_repository(tmp_path)
    manifest = tmp_path / 'pyproject.toml'
    manifest.write_text('[project]\nname = "x"\n', encoding='utf-8')
    (tmp_path / 'uv.lock').write_text('version = 1\n', encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'pyproject.toml', 'uv.lock')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')
    manifest.write_text('[project]\nname = "y"\n', encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'pyproject.toml')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['check_lockfile_sync.py'])
    monkeypatch.setattr(
        lockfile_checks, 'run_process', _uv_exiting(2, 'error: tunnel error')
    )

    assert check_lockfile_sync.main() == 2
    errors = capsys.readouterr().err
    assert 'ERROR [DEPENDENCY_SYNC]' in errors
    assert 'tunnel error' in errors


def test_infrastructure_errors_are_redacted_and_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """uv can echo index credentials and very long resolver output."""
    password, token = secrets.token_hex(12), secrets.token_hex(12)
    index = (
        'https://' + f'user:{password}' + '@index.invalid/simple/'
        f'?access_token={token}'
    )
    monkeypatch.setattr(
        lockfile_checks,
        'run_process',
        _uv_exiting(2, f'error: Failed to fetch: {index}\n' + 'r' * 6000),
    )

    with pytest.raises(lockfile_checks.LockfileInfrastructureError) as caught:
        _check(tmp_path)

    message = str(caught.value)
    detail = message.split('(uv.lock): ', maxsplit=1)[1]
    assert password not in message
    assert token not in message
    assert 'error: Failed to fetch: https://***@index.invalid' in message
    assert len(detail) <= DIAGNOSTIC_LIMIT
