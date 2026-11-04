"""Actual pytest sessions enforce release evidence requirements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.process_runner import run_process

pytestmark = pytest.mark.integration
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    'body,required,expected',
    [
        ('def helper():\n    return 1\n', '', 1),
        (
            'import pytest\n'
            '@pytest.mark.skip(reason="skip-reason: all-skipped rejection")\n'
            'def test_required():\n    assert True\n',
            '',
            1,
        ),
        ('def test_required():\n    assert 2 + 2 == 4\n', 'test_missing', 1),
        ('def test_required():\n    assert 2 + 2 == 4\n', 'test_required', 0),
    ],
)
def test_release_plugin_enforces_real_pytest_outcomes(
    tmp_path: Path, body: str, required: str, expected: int
) -> None:
    """Run the actual plugin, including empty and all-skipped subprocesses."""
    test_file = tmp_path / 'test_generated.py'
    test_file.write_text(body)
    config = tmp_path / 'pytest.ini'
    config.write_text('[pytest]\n')
    evidence = tmp_path / 'results.json'
    command = [
        'python',
        '-m',
        'pytest',
        '-c',
        str(config),
        str(test_file),
        '-p',
        'tests.support.release_evidence',
        '--release-evidence',
        str(evidence),
    ]
    if required:
        command.extend(['--release-required-case', required])

    result = run_process(command, cwd=REPOSITORY_ROOT, check=False)

    assert result.returncode == expected, result.stdout + result.stderr
    report = json.loads(evidence.read_text())
    assert report['status'] == ('passed' if expected == 0 else 'failed')
    assert (report['exit_code'] == 0) is (expected == 0)
