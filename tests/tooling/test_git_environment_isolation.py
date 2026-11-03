"""Git-hook environments must not redirect tests into the caller's repo."""

import os
from pathlib import Path

import pytest

from scripts.process_runner import run_process

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('variable', ['GIT_DIR', 'GIT_INDEX_FILE'])
def test_nested_git_repositories_preserve_the_callers_index_and_config(
    tmp_path: Path, variable: str
) -> None:
    """Real gate tests cannot write through inherited repository pointers."""
    caller = tmp_path / 'caller'
    caller.mkdir()
    for arguments in [
        ['init', '--quiet'],
        ['config', 'user.name', 'Caller Identity'],
        ['config', 'user.email', 'caller@example.invalid'],
    ]:
        run_process(['git', *arguments], cwd=caller)
    (caller / 'sentinel.txt').write_text('caller data\n', encoding='utf-8')
    run_process(['git', 'add', '--', 'sentinel.txt'], cwd=caller)
    index = caller / '.git' / 'index'
    config = caller / '.git' / 'config'
    index_before, config_before = index.read_bytes(), config.read_bytes()
    environment = {
        name: os.environ[name]
        for name in ('PATH', 'SYSTEMROOT', 'TMP', 'TEMP', 'TMPDIR')
        if name in os.environ
    }
    environment[variable] = str(
        caller / '.git' if variable == 'GIT_DIR' else index
    )
    cases = [
        'test_diff_sanity_rejects_new_debug_artifacts',
        'test_diff_sanity_rejects_inline_debug_and_stub_authorizations',
        'test_diff_sanity_does_not_flag_its_detector_source',
    ]

    result = run_process(
        [
            'python',
            '-m',
            'pytest',
            '--no-cov',
            '-q',
            '-o',
            'addopts=',
            '-o',
            f'cache_dir={tmp_path / "pytest-cache"}',
            *[
                f'tests/tooling/test_local_quality_gates.py::{case}'
                for case in cases
            ],
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )

    assert index.read_bytes() == index_before
    assert config.read_bytes() == config_before
    assert result.returncode == 0, result.stdout + result.stderr
    assert '8 passed' in result.stdout
