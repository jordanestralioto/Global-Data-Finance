"""Behavioral checks for the repository commit message gate."""

from pathlib import Path

import pytest

from scripts.check_commit_msg import main, valid_additional_rules
from scripts.process_runner import run_process


@pytest.mark.unit
@pytest.mark.parametrize(
    ('subject', 'expected'),
    [
        ('feat: add audit proof', True),
        ('fix(core): preserve result', True),
        ('Merge branch develop', True),
        ('Revert accidental change.', True),
        ('feat: add audit proof.', False),
        ('arbitrary message', True),
        ('feat: ' + 'a' * 495, False),
        ('feat: ' + 'a' * 494, True),
    ],
)
def test_additional_subject_policy(subject: str, expected: bool) -> None:
    assert valid_additional_rules(subject) is expected


@pytest.mark.unit
def test_hook_reads_only_the_subject_line(tmp_path: Path) -> None:
    message = tmp_path / 'COMMIT_EDITMSG'
    message.write_text('feat: add audit proof\n\nBody.\n', encoding='utf-8')

    assert main([str(message)]) == 0


@pytest.mark.unit
def test_hook_fails_closed_for_missing_message(tmp_path: Path) -> None:
    assert main([str(tmp_path / 'missing')]) == 2


@pytest.mark.integration
@pytest.mark.parametrize(
    ('subject', 'shared_code', 'policy_code'),
    [
        ('feat: add audit proof', 0, 0),
        ('arbitrary message', 1, 0),
        ('feat: trailing period.', 0, 1),
        ('feat: ' + 'a' * 495, 0, 1),
        ('Merge branch develop.', 0, 0),
    ],
)
def test_shared_validator_and_local_policy_compose(
    tmp_path: Path,
    subject: str,
    shared_code: int,
    policy_code: int,
) -> None:
    message = tmp_path / 'COMMIT_EDITMSG'
    message.write_text(subject + '\n', encoding='utf-8')
    repository = Path(__file__).resolve().parents[2]

    result = run_process(
        ['bash', '.agents/scripts/validate-commit-msg.sh', str(message)],
        cwd=repository,
        check=False,
    )

    assert result.returncode == shared_code
    assert main([str(message)]) == policy_code
