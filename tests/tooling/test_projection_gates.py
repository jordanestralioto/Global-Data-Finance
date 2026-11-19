"""Local quality gates on the tracked .agents projection.

Hooks execute scripts from the projection, so diff-sanity keeps its security
checks there and shell-syntax parses its scripts. Only the debug and stub
classifier, test integrity, and lockfile sync skip it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.git_repository import (
    initialize_git_repository,
    run_gate,
    run_git,
)

SCRIPTS = Path(__file__).parents[2] / 'scripts'
DIFF_SANITY = SCRIPTS / 'check_diff_sanity.py'
TEST_INTEGRITY = SCRIPTS / 'check_test_integrity.py'
LOCKFILE_SYNC = SCRIPTS / 'check_lockfile_sync.py'
SHELL_SYNTAX = SCRIPTS / 'check-shell-syntax.py'

pytestmark = pytest.mark.unit


def _commit_baseline(repo: Path) -> None:
    """Commit one clean source file as the base of a range."""
    source = repo / 'src' / 'example.py'
    source.parent.mkdir()
    source.write_text(
        'def example() -> None:\n    return None\n', encoding='utf-8'
    )
    run_git(repo, 'add', '--', 'src/example.py')
    run_git(repo, 'commit', '--quiet', '-m', 'baseline')


def _stage_projection_operations(repo: Path) -> tuple[str, str]:
    """Stage projection files carrying an operational and a lint bypass."""
    guide = '.agents/skills/demo/SKILL.md'
    tool = '.agents/scripts/tool.py'
    (repo / guide).parent.mkdir(parents=True)
    (repo / guide).write_text(
        'Never run `git commit ' + '--' + 'no-verify`.\n', encoding='utf-8'
    )
    (repo / tool).parent.mkdir(parents=True)
    (repo / tool).write_text('VALUE = 1  ' + '# ' + 'noqa\n', encoding='utf-8')
    run_git(repo, 'add', '--', guide, tool)
    return guide, tool


def test_generic_gates_skip_projection_debug_tests_and_manifests(
    tmp_path: Path,
) -> None:
    """The projection skips debug, test, and lockfile rules, not syntax."""
    initialize_git_repository(tmp_path)
    projection = tmp_path / '.agents'
    projection.mkdir()
    focused_test = 'test' + '.only'
    debug_call = 'breakpoint' + '()'
    (projection / 'test_candidate.py').write_text(
        'def test_candidate() -> None:\n'
        f'    breakpoint_call = {focused_test!r}\n'
        f'    {debug_call}\n'
        '    del breakpoint_call\n',
        encoding='utf-8',
    )
    (projection / 'hook.sh').write_text(
        '#!/usr/bin/env bash\nif true; then\n  :\nfi\n', encoding='utf-8'
    )
    (projection / 'pyproject.toml').write_text(
        '[project]\nname = "generated-harness"\nversion = "0.1.0"\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', '.')

    for script in (
        DIFF_SANITY,
        TEST_INTEGRITY,
        LOCKFILE_SYNC,
        SHELL_SYNTAX,
    ):
        result = run_gate(script, tmp_path)
        assert result.returncode == 0, result.stderr


def test_diff_sanity_scans_the_projection_for_bypasses(
    tmp_path: Path,
) -> None:
    """Hooks run projected scripts, so their bypasses stay blocking."""
    initialize_git_repository(tmp_path)
    guide, tool = _stage_projection_operations(tmp_path)

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert f'{guide}:1: [SECURITY]' in result.stderr
    assert f'{tool}:1:' in result.stderr


def test_diff_sanity_scans_projection_bypasses_in_an_explicit_range(
    tmp_path: Path,
) -> None:
    """The cumulative CI range must still block projected bypasses."""
    initialize_git_repository(tmp_path)
    _commit_baseline(tmp_path)
    guide, tool = _stage_projection_operations(tmp_path)
    run_git(tmp_path, 'commit', '--quiet', '-m', 'generated harness')

    result = run_gate(DIFF_SANITY, tmp_path, '--range', 'HEAD~1...HEAD')

    assert result.returncode == 1
    assert f'{guide}:1: [SECURITY]' in result.stderr
    assert f'{tool}:1:' in result.stderr


def test_shell_syntax_checks_projected_scripts(tmp_path: Path) -> None:
    """A projected script that a hook executes must parse."""
    initialize_git_repository(tmp_path)
    script = tmp_path / '.agents' / 'scripts' / 'hook.sh'
    script.parent.mkdir(parents=True)
    script.write_text('#!/usr/bin/env bash\nif true; then\n', encoding='utf-8')
    run_git(tmp_path, 'add', '--', '.agents/scripts/hook.sh')

    result = run_gate(SHELL_SYNTAX, tmp_path)

    assert result.returncode == 1
    assert '.agents/scripts/hook.sh' in result.stdout + result.stderr
