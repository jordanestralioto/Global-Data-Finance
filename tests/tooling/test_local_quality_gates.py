"""Regression tests for repository-local quality gate entry points."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
PRE_COMMIT_CONFIG = REPOSITORY_ROOT / '.pre-commit-config.yaml'
PIPELINE_CONFIG = REPOSITORY_ROOT / '.github' / 'workflows' / 'pipeline.yml'
GITLEAKS_CONFIG = REPOSITORY_ROOT / '.gitleaks.toml'
AGENTS_VALIDATOR = (
    REPOSITORY_ROOT
    / '.agents'
    / 'skills'
    / 'agents-md-author'
    / 'scripts'
    / 'validate_agents_md.py'
)


class ProcessResult(Protocol):
    """Captured result shape returned by the repository process adapter."""

    returncode: int
    stdout: str
    stderr: str


run_process = cast(
    Callable[..., ProcessResult],
    import_module('scripts.process_runner').run_process,
)
DIFF_SANITY = REPOSITORY_ROOT / 'scripts' / 'check_diff_sanity.py'
DIFF_SANITY_POLICY = REPOSITORY_ROOT / 'scripts' / 'diff_sanity_policy.py'
TEST_INTEGRITY = REPOSITORY_ROOT / 'scripts' / 'check_test_integrity.py'
LOCKFILE_SYNC = REPOSITORY_ROOT / 'scripts' / 'check_lockfile_sync.py'
SHELL_SYNTAX = REPOSITORY_ROOT / 'scripts' / 'check-shell-syntax.py'


pytestmark = pytest.mark.unit


def run_git(repo: Path, *args: str) -> ProcessResult:
    """Run a Git command in an isolated test repository."""
    return run_process(['git', *args], cwd=repo)


def initialize_git_repository(repo: Path) -> None:
    """Initialize a disposable repository with deterministic metadata."""
    run_git(repo, 'init', '--quiet')
    run_git(repo, 'config', 'user.name', 'Quality Gate Tests')
    run_git(repo, 'config', 'user.email', 'quality-gates@example.invalid')


def run_gate(script: Path, repo: Path, *arguments: str) -> ProcessResult:
    """Execute a gate script from an isolated repository."""
    return run_process(
        ['python', str(script), *arguments],
        cwd=repo,
        check=False,
    )


def staged_test_patch_hash(repo: Path) -> str:
    """Return the checker-authored hash for the staged test patch."""
    result = run_gate(TEST_INTEGRITY, repo, '--print-hash')
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    return lines[0].rsplit(maxsplit=1)[1]


def stage_assertion_reduction_policy(
    repo: Path,
    *,
    entries: object,
    alias: object | None = None,
) -> None:
    """Stage a policy document for an isolated integrity-gate repository."""
    policy: dict[str, object] = {
        'allowed_deletions': {},
        'allowed_assertion_reductions': entries,
    }
    if alias is not None:
        policy['allowed_reductions'] = alias
    policy_path = repo / '.test-integrity-policy.json'
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    run_git(repo, 'add', '--', '.test-integrity-policy.json')


def hook_block(content: str, hook_id: str) -> str:
    """Return one hook block from the YAML configuration."""
    match = re.search(
        rf'(?ms)^[ ]+- id: {re.escape(hook_id)}\n.*?(?=^[ ]+- id: |\Z)',
        content,
    )
    if match is None:
        raise AssertionError(f'Missing hook: {hook_id}')
    return match.group(0)


def configured_print_files(content: str) -> set[str]:
    """Extract file-scoped raw-output permissions from YAML or shell text."""
    marker = '--allow-print-file'
    lines = content.splitlines()
    paths: set[str] = set()
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        candidate = line.split(marker, maxsplit=1)[1].strip()
        if candidate in {'', '\\'}:
            for following in lines[index + 1 :]:
                candidate = following.strip()
                if not candidate or candidate.startswith('#'):
                    continue
                if candidate.startswith('- '):
                    candidate = candidate[2:].strip()
                break
        candidate = candidate.rstrip('\\').strip().strip('"\'')
        if candidate:
            paths.add(
                candidate.replace(
                    '$app_dir/', 'src/globaldatafinance/application/'
                )
            )
    return paths


def test_precommit_configuration_preserves_the_quality_gate_contract() -> None:
    """The hook file must keep the staged, manual, and pre-push boundaries."""
    content = PRE_COMMIT_CONFIG.read_text(encoding='utf-8')

    assert 'minimum_pre_commit_version: "4.3.0"' in content
    assert 'exclude: |' in content
    for root in (
        r'\.agents/',
        r'\.claude/',
        r'\.codex/',
        r'\.opencode/',
        r'\.github/prompts/',
    ):
        assert root in content
    assert 'id: validate-agents-md' in content
    assert 'validate_agents_md.py' in content
    assert 'files: ^AGENTS\\.md$' in content
    assert 'stages: [manual]' in content
    assert 'id: test-quality' in content
    assert 'scripts/check_test_quality.py' in content
    assert 'stages: [pre-commit, pre-push]' in hook_block(
        content, 'test-quality'
    )
    assert 'entry: harness-sync --check' in content
    assert 'entry: uv lock --check' in content
    assert 'id: import-cycles' in content
    assert 'id: import-linter' in content
    assert 'exclude: ^tests/support/' in hook_block(content, 'name-tests-test')
    assert 'entry: uv run --locked --no-sync pip-audit --timeout 60' in content
    assert (
        'files: ^(?:src|tests|scripts|examples)/.*\\.(?:py|pyi|pyw|sh|bash)$'
        in content
    )
    assert 'args: [--redact, --config=.gitleaks.toml]' in content


def test_diff_sanity_print_allowlist_matches_ci() -> None:
    """Pre-commit and CI must authorize exactly the same CLI output files."""
    pre_commit = configured_print_files(
        hook_block(
            PRE_COMMIT_CONFIG.read_text(encoding='utf-8'), 'diff-sanity'
        )
    )
    ci = configured_print_files(PIPELINE_CONFIG.read_text(encoding='utf-8'))

    assert pre_commit == ci
    assert 'scripts/check_test_quality.py' in pre_commit


def test_mutating_hooks_keep_projection_exclusions() -> None:
    """Every mutating file hook must independently exclude projections."""
    content = PRE_COMMIT_CONFIG.read_text(encoding='utf-8')
    roots = (
        r'\.agents/',
        r'\.claude/',
        r'\.codex/',
        r'\.opencode/',
        r'\.github/prompts/',
    )

    for hook_id in (
        'trailing-whitespace',
        'end-of-file-fixer',
        'mixed-line-ending',
        'ruff-check',
        'ruff-format',
        'mdformat',
    ):
        block = hook_block(content, hook_id)
        assert all(root in block for root in roots), hook_id

    mdformat_block = hook_block(content, 'mdformat')
    assert 'docs/' in mdformat_block
    assert 'openspec/' in mdformat_block


def test_gitleaks_policy_only_excludes_external_harness_roots() -> None:
    """The project gitleaks policy must keep product paths in scope."""
    content = GITLEAKS_CONFIG.read_text(encoding='utf-8')

    assert 'useDefault = true' in content
    assert 'description = "Developer-owned harness projections"' in content
    for root in (
        r'^\.agents/',
        r'^\.claude/',
        r'^\.codex/',
        r'^\.opencode/',
        r'^\.github/prompts/',
    ):
        assert root in content
    assert 'src/' not in content
    assert 'tests/' not in content


def test_agents_hook_validator_rejects_an_invalid_document(
    tmp_path: Path,
) -> None:
    """The tracked validator must fail closed for malformed AGENTS.md input."""
    invalid_agents = tmp_path / 'AGENTS.md'
    invalid_agents.write_text('# invalid\n', encoding='utf-8')

    result = run_process(
        [
            'python',
            str(AGENTS_VALIDATOR),
            '--file',
            str(invalid_agents),
            '--strict-governance',
        ],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode == 1
    assert (
        'level-2 headings must match portable contract order' in result.stdout
    )


def test_diff_sanity_rejects_new_debug_artifacts(tmp_path: Path) -> None:
    """The diff gate must reject debug calls added to authored Python code."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    debug_call = 'breakpoint' + '()'
    source.write_text(
        f'def example() -> None:\n    {debug_call}\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[DEBUG]' in result.stderr
    assert 'breakpoint' in result.stderr


_BREAKPOINT_CALL = 'breakpoint' + '()'
_CONSOLE_LOG_CALL = 'console' + '.log()'
_PRINT_CALL = 'print' + "('output')"
_TODO_EXCEPTION = 'NotImplementedError' + '("TODO")'
_TODO_STUB = 'pass  # ' + 'TODO'
_ALLOW_DEBUG = 'allow-' + 'debug: local investigation'
_ALLOW_STUB = 'allow-' + 'stub: temporary'
_STUB_REASON = 'stub-' + 'reason: temporary'
_TODO_REASON = 'todo-' + 'reason: temporary'


@pytest.mark.parametrize(
    ('filename', 'content', 'expected_category'),
    [
        pytest.param(
            'src/example.py',
            (
                'def calculate() -> None:\n'
                f'    {_BREAKPOINT_CALL}  # {_ALLOW_DEBUG}\n'
            ),
            '[DEBUG]',
        ),
        pytest.param(
            'src/example.js',
            f'{_CONSOLE_LOG_CALL}  # {_ALLOW_DEBUG}\n',
            '[DEBUG]',
        ),
        pytest.param(
            'src/example.py', f'{_PRINT_CALL}  # {_ALLOW_DEBUG}\n', '[DEBUG]'
        ),
        pytest.param(
            'src/example.py',
            (
                'def calculate() -> None:\n'
                f'    raise {_TODO_EXCEPTION}  # {_ALLOW_STUB}\n'
            ),
            '[STUB]',
        ),
        pytest.param(
            'src/example.py', f'{_TODO_STUB}  # {_STUB_REASON}\n', '[STUB]'
        ),
        pytest.param(
            'src/example.py', f'{_TODO_STUB}  # {_TODO_REASON}\n', '[STUB]'
        ),
    ],
)
def test_diff_sanity_rejects_inline_debug_and_stub_authorizations(
    tmp_path: Path,
    filename: str,
    content: str,
    expected_category: str,
) -> None:
    """Inline comments never authorize debug output or placeholder stubs."""
    initialize_git_repository(tmp_path)
    source = tmp_path / filename
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding='utf-8')
    run_git(tmp_path, 'add', '--', filename)

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert expected_category in result.stderr


def test_diff_sanity_does_not_flag_its_detector_source(tmp_path: Path) -> None:
    """The detector must not reject its own encoded rule definitions."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'scripts' / 'check_diff_sanity.py'
    source.parent.mkdir()
    source.write_text(
        DIFF_SANITY.read_text(encoding='utf-8'), encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'scripts/check_diff_sanity.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 0, result.stderr


def test_diff_sanity_does_not_flag_its_policy_source(tmp_path: Path) -> None:
    """The extracted policy module must also be safe for self-validation."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'scripts' / 'diff_sanity_policy.py'
    source.parent.mkdir()
    source.write_text(
        DIFF_SANITY_POLICY.read_text(encoding='utf-8'), encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'scripts/diff_sanity_policy.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 0, result.stderr


def test_generic_gates_ignore_all_external_harness_roots(
    tmp_path: Path,
) -> None:
    """Generic staged gates must not inspect generated harness projections."""
    initialize_git_repository(tmp_path)
    external_roots = (
        '.agents',
        '.claude',
        '.codex',
        '.opencode',
        '.github/prompts',
    )
    focused_test = 'test' + '.only'
    debug_call = 'breakpoint' + '()'
    for root in external_roots:
        candidate = tmp_path / root / 'test_candidate.py'
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(
            'def test_candidate() -> None:\n'
            f'    breakpoint_call = {focused_test!r}\n'
            f'    {debug_call}\n'
            '    del breakpoint_call\n',
            encoding='utf-8',
        )
        shell_candidate = candidate.with_suffix('.sh')
        shell_candidate.write_text(
            '#!/usr/bin/env bash\nif true; then\n', encoding='utf-8'
        )
    external_manifest = tmp_path / '.agents' / 'pyproject.toml'
    external_manifest.write_text(
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


def test_diff_sanity_rejects_unconfigured_console_output_in_examples(
    tmp_path: Path,
) -> None:
    """A console example needs an explicit file-scoped permission."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'examples' / 'example.py'
    source.parent.mkdir()
    print_name = 'print'
    source.write_text(f"{print_name}('example output')\n", encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'examples/example.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[DEBUG]' in result.stderr


def test_diff_sanity_allows_console_output_in_examples(tmp_path: Path) -> None:
    """Runnable examples may print user-facing progress and result messages."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'examples' / 'example.py'
    source.parent.mkdir()
    print_name = 'print'
    source.write_text(f"{print_name}('example output')\n", encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'examples/example.py')

    result = run_gate(
        DIFF_SANITY,
        tmp_path,
        '--allow-print-file',
        'examples/example.py',
    )

    assert result.returncode == 0, result.stderr


def test_diff_sanity_rejects_type_bypass_with_an_empty_reason(
    tmp_path: Path,
) -> None:
    """An empty bypass annotation must not authorize suppression."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    type_ignore = '# type: ' + 'ignore'
    empty_reason = 'allow-' + 'bypass:'
    source.write_text(
        f'value = missing  {type_ignore}[name]  # {empty_reason}\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[BYPASS]' in result.stderr


def test_diff_sanity_never_allows_noqa(tmp_path: Path) -> None:
    """A linter suppression remains rejected even with a stated rationale."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    noqa_marker = '# ' + 'noqa'
    bypass_reason = 'allow-' + 'bypass: reviewed exception'
    source.write_text(
        f'import unused  {noqa_marker}: F401  # {bypass_reason}\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[BYPASS]' in result.stderr


def test_diff_sanity_never_allows_type_bypass_with_a_reason(
    tmp_path: Path,
) -> None:
    """A rationale cannot authorize an executable type-check bypass."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    type_ignore = '# type: ' + 'ignore'
    source.write_text(
        f'value = missing  {type_ignore}  # reviewed boundary\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[BYPASS]' in result.stderr


def test_diff_sanity_scans_an_explicit_commit_range(tmp_path: Path) -> None:
    """The CI range mode must detect a violation after the index is empty."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    source.write_text(
        'def example() -> None:\n    return None\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    debug_call = 'breakpoint' + '()'
    source.write_text(
        f'def example() -> None:\n    {debug_call}\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'add debug artifact')

    result = run_gate(DIFF_SANITY, tmp_path, '--range', 'HEAD~1...HEAD')

    assert result.returncode == 1
    assert '[DEBUG]' in result.stderr


def test_diff_sanity_ignores_external_harness_in_an_explicit_range(
    tmp_path: Path,
) -> None:
    """Range mode must apply the same projection filter as staged mode."""
    initialize_git_repository(tmp_path)
    source = tmp_path / 'src' / 'example.py'
    source.parent.mkdir()
    source.write_text(
        'def example() -> None:\n    return None\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'src/example.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    debug_call = 'breakpoint' + '()'
    external = tmp_path / '.agents' / 'generated.py'
    external.parent.mkdir()
    external.write_text(f'def generated() -> None:\n    {debug_call}\n')
    run_git(tmp_path, 'add', '--', '.agents/generated.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'generated harness')

    result = run_gate(DIFF_SANITY, tmp_path, '--range', 'HEAD~1...HEAD')

    assert result.returncode == 0
    assert 'SKIP' in result.stdout


@pytest.mark.parametrize(
    ('filename', 'content'),
    [
        (
            'config.yaml',
            f'value: 1 {"# " + "noqa"}\n',
        ),
        (
            'config.toml',
            f'value = 1 {"# type: " + "ignore"}\n',
        ),
        (
            'config.json',
            '{"value": "' + '@' + 'ts-expect-error"}\n',
        ),
    ],
)
def test_diff_sanity_rejects_bypasses_in_text_configuration(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    """Compiler and linter bypasses are forbidden in configuration formats."""
    initialize_git_repository(tmp_path)
    config = tmp_path / filename
    config.write_text(content, encoding='utf-8')
    run_git(tmp_path, 'add', '--', filename)

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[BYPASS]' in result.stderr


def test_diff_sanity_allows_documentary_bypass_citations(
    tmp_path: Path,
) -> None:
    """Markdown may explain suppression markers as non-executable examples."""
    initialize_git_repository(tmp_path)
    noqa_marker = '# ' + 'noqa'
    type_ignore = '# type: ' + 'ignore'
    readme = tmp_path / 'README.md'
    readme.write_text(
        f'This guide mentions {noqa_marker} and {type_ignore}.\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'README.md')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    'content',
    [
        f'{"continue-" + "on-error"}: true\n',
        f'{"SKIP" + "="}diff-sanity\n',
        f'curl https://example.invalid {"| " + "bash"}\n',
        f'run: command {"||" + " true"}\n',
    ],
)
def test_diff_sanity_rejects_operational_bypasses_in_text(
    tmp_path: Path,
    content: str,
) -> None:
    """Operational bypasses remain blocked regardless of file extension."""
    initialize_git_repository(tmp_path)
    config = tmp_path / 'workflow.yaml'
    config.write_text(content, encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'workflow.yaml')

    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 1
    assert '[SECURITY]' in result.stderr


def test_diff_sanity_returns_error_when_git_cannot_be_inspected(
    tmp_path: Path,
) -> None:
    """Git infrastructure failures must fail closed with status two."""
    result = run_gate(DIFF_SANITY, tmp_path)

    assert result.returncode == 2
    assert 'ERROR [DIFF_SANITY]' in result.stderr


def test_test_integrity_rejects_focus_skip_and_assertion_reduction(
    tmp_path: Path,
) -> None:
    """The test gate must detect weakened and focused tests in one diff."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_example.py'
    test_file.parent.mkdir()
    original = (
        'def test_example() -> None:\n    assert 1 == 1\n    assert 2 == 2\n'
    )
    test_file.write_text(original, encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'tests/test_example.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    focused_test = 'test' + '.only'
    skipped_marker = '@pytest.mark.' + 'skip'
    weakened = (
        'def test_example() -> None:\n'
        '    assert 1 == 1\n'
        f'    {focused_test}("example")\n'
        f'    {skipped_marker}\n'
    )
    test_file.write_text(weakened, encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'tests/test_example.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_FOCUS]' in result.stderr
    assert '[TEST_SKIP]' in result.stderr
    assert '[TEST_INTEGRITY]' in result.stderr


def test_test_integrity_rejects_pytest_context_assertion_removal(
    tmp_path: Path,
) -> None:
    """Removing a pytest exception assertion is test erosion."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_example.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'import pytest\n\n'
        'def test_error() -> None:\n'
        '    with pytest.raises(ValueError):\n'
        '        raise ValueError("expected")\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_example.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.write_text(
        'def test_error() -> None:\n    raise ValueError("expected")\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_example.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_INTEGRITY]' in result.stderr


def test_test_integrity_rejects_a_test_renamed_outside_test_scope(
    tmp_path: Path,
) -> None:
    """A test moved into production code is modeled as a deletion."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_security.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_security() -> None:\n    assert True\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'tests/test_security.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    retired_file = tmp_path / 'src' / 'retired_test.py'
    retired_file.parent.mkdir()
    run_git(tmp_path, 'mv', 'tests/test_security.py', 'src/retired_test.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_DELETION]' in result.stderr


def test_test_integrity_scans_a_rename_in_an_explicit_range(
    tmp_path: Path,
) -> None:
    """The CI range mode must retain the same rename-to-deletion protection."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_security.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_security() -> None:\n    assert True\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'tests/test_security.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    retired_file = tmp_path / 'src' / 'retired_test.py'
    retired_file.parent.mkdir()
    run_git(tmp_path, 'mv', 'tests/test_security.py', 'src/retired_test.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'retire test')

    result = run_gate(TEST_INTEGRITY, tmp_path, '--range', 'HEAD~1...HEAD')

    assert result.returncode == 1
    assert '[TEST_DELETION]' in result.stderr


def test_test_integrity_requires_authorization_for_deleted_tests(
    tmp_path: Path,
) -> None:
    """The test gate must require a staged reason for deleting test files."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_removed.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_removed() -> None:\n    assert True\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'tests/test_removed.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.unlink()
    run_git(tmp_path, 'add', '--update')
    denied = run_gate(TEST_INTEGRITY, tmp_path)
    assert denied.returncode == 1
    assert '[TEST_DELETION]' in denied.stderr

    policy = {
        'allowed_deletions': {
            'tests/test_removed.py': (
                'Superseded by the consolidated fixture suite.'
            )
        }
    }
    (tmp_path / '.test-deletions.json').write_text(
        json.dumps(policy), encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', '.test-deletions.json')
    approved = run_gate(TEST_INTEGRITY, tmp_path)

    assert approved.returncode == 0


def test_test_integrity_rejects_stale_deletion_policy_entries(
    tmp_path: Path,
) -> None:
    """A policy entry must describe a deletion in the inspected diff."""
    initialize_git_repository(tmp_path)
    policy = {
        'allowed_deletions': {
            'tests/test_removed.py': 'The replacement suite is canonical.'
        }
    }
    (tmp_path / '.test-integrity-policy.json').write_text(
        json.dumps(policy), encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', '.test-integrity-policy.json')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline policy')

    (tmp_path / 'README.md').write_text(
        'Unrelated change.\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'README.md')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_POLICY]' in result.stderr
    assert 'stale deletion authorization' in result.stderr


def test_lockfile_sync_requires_uv_lock_for_a_pyproject_change(
    tmp_path: Path,
) -> None:
    """An unrelated requirements file cannot satisfy the uv lock gate."""
    initialize_git_repository(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[project]\nname = "quality-test"\nversion = "0.1.0"\n',
        encoding='utf-8',
    )
    (tmp_path / 'requirements.txt').write_text('pytest\n', encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'pyproject.toml', 'requirements.txt')

    result = run_gate(LOCKFILE_SYNC, tmp_path)

    assert result.returncode == 1
    assert 'uv.lock' in result.stderr


def test_lockfile_sync_skips_unrelated_staged_changes(tmp_path: Path) -> None:
    """The lock gate must ignore unrelated staged documentation changes."""
    initialize_git_repository(tmp_path)
    (tmp_path / 'README.md').write_text('Documentation.\n', encoding='utf-8')
    run_git(tmp_path, 'add', '--', 'README.md')

    result = run_gate(LOCKFILE_SYNC, tmp_path)

    assert result.returncode == 0
    assert 'SKIP' in result.stdout


@pytest.mark.parametrize('script', [DIFF_SANITY, TEST_INTEGRITY, SHELL_SYNTAX])
def test_gates_skip_when_no_relevant_staged_change(
    tmp_path: Path, script: Path
) -> None:
    """Each staged-file gate must skip safely when there is no work."""
    initialize_git_repository(tmp_path)
    (tmp_path / 'README.md').write_text(
        'No relevant change.\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'README.md')

    result = run_gate(script, tmp_path)

    assert result.returncode == 0


def test_test_integrity_policy_not_read_from_disk_for_range(
    tmp_path: Path,
) -> None:
    """Policy present only on disk must not authorize changes in a range."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert True\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.unlink()
    run_git(tmp_path, 'add', '--update')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'remove test')

    policy = {
        'allowed_deletions': {
            'tests/test_guarded.py': 'Superseded by new suite.',
        },
    }
    (tmp_path / '.test-integrity-policy.json').write_text(
        json.dumps(policy), encoding='utf-8'
    )

    result = run_gate(TEST_INTEGRITY, tmp_path, '--range', 'HEAD~1...HEAD')

    assert result.returncode == 1, (
        'policy on disk must not authorize deletions in a committed range'
    )
    assert '[TEST_DELETION]' in result.stderr


def test_test_integrity_policy_not_read_from_disk_for_staged(
    tmp_path: Path,
) -> None:
    """Policy present only on disk must not authorize staged changes."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_staged.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_staged() -> None:\n    assert True\n', encoding='utf-8'
    )
    run_git(tmp_path, 'add', '--', 'tests/test_staged.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.unlink()
    run_git(tmp_path, 'add', '--update')

    policy = {
        'allowed_deletions': {
            'tests/test_staged.py': 'Superseded by new suite.',
        },
    }
    (tmp_path / '.test-integrity-policy.json').write_text(
        json.dumps(policy), encoding='utf-8'
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1, (
        'policy on disk must not authorize deletions in the staged index'
    )
    assert '[TEST_DELETION]' in result.stderr
