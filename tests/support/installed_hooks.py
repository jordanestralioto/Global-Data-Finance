"""Install one repository gate as a real pre-commit hook in a test repo."""

from __future__ import annotations

import json
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.process_runner import ProcessResult, run_process


def hook_environment(home: Path) -> dict[str, str]:
    """Return an environment free of an enclosing hook's state."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith('PRE_COMMIT') and key != 'SKIP'
    }
    environment['PRE_COMMIT_HOME'] = str(home)
    return environment


def run_with_hooks(repo: Path, home: Path, *command: str) -> ProcessResult:
    """Run a command whose Git hooks use an isolated pre-commit store."""
    return run_process(
        list(command), cwd=repo, env=hook_environment(home), check=False
    )


def install_local_hooks(
    repo: Path,
    home: Path,
    *,
    stage: str,
    hooks: Sequence[tuple[str, Sequence[str]]],
) -> None:
    """Configure local hooks that run in order for a stage and install them.

    Raises:
        AssertionError: If pre-commit cannot install the hooks.
    """
    configuration = ['repos:\n  - repo: local\n    hooks:\n']
    for hook_id, command in hooks:
        configuration.append(
            f'      - id: {hook_id}\n        name: {hook_id}\n'
            f'        entry: {json.dumps(shlex.join(command))}\n'
            '        language: system\n        pass_filenames: false\n'
            f'        always_run: true\n        stages: [{stage}]\n'
        )
    (repo / '.pre-commit-config.yaml').write_text(
        ''.join(configuration), encoding='utf-8'
    )
    installed = run_with_hooks(
        repo,
        home,
        'python',
        '-m',
        'pre_commit',
        'install',
        '--hook-type',
        stage,
    )
    if installed.returncode != 0:
        raise AssertionError(installed.stdout + installed.stderr)


def install_local_hook(
    repo: Path, home: Path, *, hook_id: str, script: Path, stage: str
) -> None:
    """Configure and install one gate script as a local hook for a stage.

    Raises:
        AssertionError: If pre-commit cannot install the hook.
    """
    install_local_hooks(
        repo,
        home,
        stage=stage,
        hooks=[(hook_id, [sys.executable, str(script)])],
    )
