"""Contract tests for the projected max-lines gate the hooks execute.

The checker belongs to the central-skills projection; these tests only run it.
They fail when the projected gate stops enforcing the production-file cap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.git_repository import (
    initialize_git_repository,
    run_gate,
    run_git,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
MAX_LINES = REPOSITORY_ROOT / '.agents' / 'scripts' / 'check-max-lines.py'
PRODUCTION_CAP = 400

pytestmark = pytest.mark.unit


def _track_module(repo: Path, line_count: int) -> str:
    """Track one production module with an exact number of lines."""
    initialize_git_repository(repo)
    module = repo / 'src' / 'package' / 'module.py'
    module.parent.mkdir(parents=True)
    module.write_text(
        ''.join(f'VALUE_{index} = {index}\n' for index in range(line_count)),
        encoding='utf-8',
    )
    relative = module.relative_to(repo).as_posix()
    run_git(repo, 'add', '--', relative)
    return relative


def test_projected_gate_accepts_a_module_at_the_cap(tmp_path: Path) -> None:
    """A production module exactly at the cap passes."""
    _track_module(tmp_path, PRODUCTION_CAP)

    result = run_gate(MAX_LINES, tmp_path, 'src')

    assert result.returncode == 0, result.stderr


def test_projected_gate_rejects_a_module_over_the_cap(tmp_path: Path) -> None:
    """One line over the production cap blocks the hook."""
    module = _track_module(tmp_path, PRODUCTION_CAP + 1)

    result = run_gate(MAX_LINES, tmp_path, 'src')

    assert result.returncode == 1
    assert module in result.stderr
