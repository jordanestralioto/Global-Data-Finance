"""Contract tests for hook scope, stages, and pinned tool versions."""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

from tests.support.precommit_config import (
    hook_block,
    hook_ids_in_order,
    hook_repository,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
PRE_COMMIT_CONFIG = REPOSITORY_ROOT / '.pre-commit-config.yaml'
UV_LOCK = REPOSITORY_ROOT / 'uv.lock'
REMOTE_PIN_RE = re.compile(
    r'(?m)^  - repo: (https://\S+)\n((?:    #.*\n)*)    rev: (\S+)'
)
MANIFEST_STAGED_HOOKS = (
    'trailing-whitespace',
    'end-of-file-fixer',
    'check-added-large-files',
    'check-executables-have-shebangs',
    'check-shebang-scripts-are-executable',
    'destroyed-symlinks',
)

pytestmark = pytest.mark.unit


def _config() -> str:
    """Return the canonical pre-commit configuration text."""
    return PRE_COMMIT_CONFIG.read_text(encoding='utf-8')


def _stages(block: str) -> list[str]:
    """Return the stages of one hook block, defaulting to commit."""
    match = re.search(r'(?m)^\s+stages: \[([^\]]*)\]$', block)
    if match is None:
        return ['pre-commit']
    return [stage.strip() for stage in match.group(1).split(',')]


def _locked_versions() -> dict[str, str]:
    """Return the version of every uv-locked package that declares one."""
    lock = tomllib.loads(UV_LOCK.read_text(encoding='utf-8'))
    return {
        package['name']: package['version']
        for package in lock['package']
        if 'version' in package
    }


def test_global_exclude_keeps_projections_visible_to_scanners() -> None:
    """Only local fixer excludes may hide the tracked .agents projection."""
    content = _config()
    global_settings = content.split('\nrepos:', maxsplit=1)[0]

    assert r'\.agents/' not in global_settings
    for hook_id in ('detect-secrets', 'detect-private-key'):
        assert r'\.agents/' not in hook_block(content, hook_id), hook_id


def test_manifest_staged_hooks_stay_off_the_push_path() -> None:
    """Hooks whose manifests also list pre-push must be pinned to commit."""
    content = _config()

    for hook_id in MANIFEST_STAGED_HOOKS:
        assert _stages(hook_block(content, hook_id)) == ['pre-commit'], hook_id


def test_push_snapshot_guard_runs_first_and_stops_the_push() -> None:
    """The snapshot guard precedes every other pre-push hook."""
    content = _config()
    pre_push_hooks = [
        hook_id
        for hook_id in hook_ids_in_order(content)
        if 'pre-push' in _stages(hook_block(content, hook_id))
    ]
    guard = hook_block(content, 'push-snapshot')

    assert pre_push_hooks[0] == 'push-snapshot'
    assert 'scripts/check_push_snapshot.py' in guard
    assert 'fail_fast: true' in guard
    assert _stages(guard) == ['pre-push']


def test_ruff_auto_fix_is_limited_to_import_order() -> None:
    """Automatic lint fixes must not rewrite code beyond import order."""
    block = hook_block(_config(), 'ruff-check')

    assert '--fixable=I' in block
    assert '--exit-non-zero-on-fix' in block
    assert '--unsafe-fixes' not in block


@pytest.mark.parametrize(
    ('hook_id', 'tool'),
    [
        ('ruff-check', 'ruff check'),
        ('ruff-format', 'ruff format'),
        ('detect-secrets', 'detect-secrets-hook'),
        ('mdformat', 'mdformat'),
    ],
)
def test_tools_shared_with_ci_run_from_the_lockfile(
    hook_id: str, tool: str
) -> None:
    """A hook for a tool CI runs from uv.lock executes that environment.

    A remote hook would install its own copy, whose version only a comment
    could vouch for.
    """
    content = _config()
    block = hook_block(content, hook_id)

    assert hook_repository(content, hook_id) == 'local'
    assert 'language: system' in block
    assert f'entry: uv run --locked --no-sync {tool}' in block
    assert 'additional_dependencies' not in block


@pytest.mark.parametrize(
    'package', ['ruff', 'detect-secrets', 'mdformat', 'mdformat-gfm']
)
def test_hook_tools_execute_the_locked_versions(package: str) -> None:
    """The environment the hooks run in holds the uv-locked versions."""
    assert metadata.version(package) == _locked_versions()[package]


def test_remote_hooks_pin_immutable_commits() -> None:
    """Remote hook repositories are pinned by commit, release in a comment."""
    pins = REMOTE_PIN_RE.findall(_config())

    assert pins
    for repository, comments, revision in pins:
        assert re.fullmatch(r'[0-9a-f]{40}', revision), repository
        assert re.search(r'#.*\bv?\d+\.\d+', comments), repository
