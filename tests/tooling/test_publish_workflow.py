"""Tests that execute the release validation script from publish.yml."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.process_runner import run_process

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_WORKFLOW = REPOSITORY_ROOT / '.github' / 'workflows' / 'publish.yml'


def extract_validator_script() -> str:
    """Extract the embedded Python script from the publish workflow."""
    content = PUBLISH_WORKFLOW.read_text(encoding='utf-8')
    match = re.search(r"python - <<'PY'\n(.*?)\n\s*PY", content, re.DOTALL)
    if match is None:
        raise AssertionError('Validator script not found in publish.yml')
    return textwrap.dedent(match.group(1))


def create_fake_gh(
    bin_dir: Path,
    *,
    exit_code: int = 0,
    stdout: str = '',
    stderr: str = '',
    log_file: Path | None = None,
) -> Path:
    """Create an executable fake gh script that logs its invocations."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / 'gh'
    log_statement = ''
    if log_file is not None:
        log_statement = (
            f'import sys\n'
            f'with open({str(log_file)!r}, "a", encoding="utf-8") as f:\n'
            f'    f.write(" ".join(sys.argv[1:]) + "\\n")\n'
        )

    code = (
        f'#!{sys.executable}\n'
        f'{log_statement}'
        f'import sys\n'
        f'if {stderr!r}:\n'
        f'    sys.stderr.write({stderr!r} + "\\n")\n'
        f'if {stdout!r}:\n'
        f'    sys.stdout.write({stdout!r} + "\\n")\n'
        f'sys.exit({exit_code})\n'
    )
    gh_path.write_text(code, encoding='utf-8')
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC)
    return gh_path


def run_validator(
    script: str,
    env: dict[str, str],
    *,
    custom_path: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    """Run the extracted validator script in an isolated subprocess."""
    output_file = env.get('GITHUB_OUTPUT')
    sub_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith('GITHUB_')
        and k
        not in {
            'EVENT_NAME',
            'RELEASE_TAG',
            'RELEASE_REF',
            'IS_PRERELEASE',
            'DRY_RUN',
        }
    }
    if custom_path is not None:
        sub_env['PATH'] = custom_path
    sub_env.update(env)

    proc = run_process(
        ['python', '-c', script],
        cwd=REPOSITORY_ROOT,
        env=sub_env,
        check=False,
    )

    outputs: dict[str, str] = {}
    if output_file and Path(output_file).exists():
        for line in Path(output_file).read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                outputs[k.strip()] = v.strip()

    return proc.returncode, proc.stderr, outputs


def test_dry_run_executes_validations_without_requiring_gh_or_release(
    tmp_path: Path,
) -> None:
    """dry_run=true must succeed without requiring gh or a GitHub release."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'true',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, outputs = run_validator(
        script, env, custom_path=str(tmp_path)
    )
    assert ret == 0, stderr
    assert outputs['release_tag'] == 'v0.2.0'
    assert outputs['release_version'] == '0.2.0'
    assert outputs['dry_run'] == 'true'


def test_dry_run_defaults_to_true_when_unset_on_workflow_dispatch(
    tmp_path: Path,
) -> None:
    """When DRY_RUN is empty or unset, workflow_dispatch defaults to true."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.3.1',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, outputs = run_validator(
        script, env, custom_path=str(tmp_path)
    )
    assert ret == 0, stderr
    assert outputs['dry_run'] == 'true'


def test_non_dry_run_fails_if_gh_cli_is_missing(tmp_path: Path) -> None:
    """Non-dry-run workflow_dispatch must fail when gh CLI is missing."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    empty_bin = tmp_path / 'empty_bin'
    empty_bin.mkdir()

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'owner/repo',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(empty_bin))
    assert ret != 0
    assert 'GitHub CLI (gh) is required' in stderr


def test_non_dry_run_fails_if_github_token_is_missing(
    tmp_path: Path,
) -> None:
    """Non-dry-run workflow_dispatch must fail when token is missing."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    create_fake_gh(bin_dir, stdout=json.dumps({'isPrerelease': False}))
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_REPOSITORY': 'owner/repo',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'GITHUB_TOKEN is required' in stderr


def test_non_dry_run_fails_if_github_repository_is_missing(
    tmp_path: Path,
) -> None:
    """Non-dry-run workflow_dispatch must fail when repository is missing."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    create_fake_gh(bin_dir, stdout=json.dumps({'isPrerelease': False}))
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'GITHUB_REPOSITORY is required' in stderr


def test_non_dry_run_fails_when_gh_release_view_query_fails(
    tmp_path: Path,
) -> None:
    """An unsuccessful gh query must fail before PyPI publication."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    log_file = tmp_path / 'gh.log'
    create_fake_gh(
        bin_dir,
        exit_code=1,
        stderr='release not found',
        log_file=log_file,
    )
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'jordanestralioto/Global-Data-Finance',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'GitHub release query failed for v0.2.0' in stderr
    assert 'release not found' in stderr
    gh_invocation = log_file.read_text(encoding='utf-8')
    assert '--repo jordanestralioto/Global-Data-Finance' in gh_invocation


def test_non_dry_run_fails_on_invalid_gh_json_response(
    tmp_path: Path,
) -> None:
    """An invalid JSON response from gh must fail before PyPI publication."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    create_fake_gh(bin_dir, stdout='Internal Error: not json')
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'owner/repo',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'Invalid JSON response from gh release view' in stderr


def test_non_dry_run_fails_when_is_prerelease_field_is_missing(
    tmp_path: Path,
) -> None:
    """A response missing isPrerelease must fail closed."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    create_fake_gh(bin_dir, stdout=json.dumps({'tag_name': 'v0.2.0'}))
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'owner/repo',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'missing "isPrerelease"' in stderr


def test_non_dry_run_rejects_prerelease_release_from_gh(
    tmp_path: Path,
) -> None:
    """When gh reports isPrerelease=true, the job must fail."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    log_file = tmp_path / 'gh.log'
    create_fake_gh(
        bin_dir,
        stdout=json.dumps({'isPrerelease': True}),
        log_file=log_file,
    )
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'owner/repo',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env, custom_path=str(bin_dir))
    assert ret != 0
    assert 'is marked as a prerelease' in stderr
    gh_call = log_file.read_text(encoding='utf-8')
    assert (
        'release view v0.2.0 --repo owner/repo --json isPrerelease' in gh_call
    )


def test_automated_release_event_rejects_prerelease(tmp_path: Path) -> None:
    """Automated release event with IS_PRERELEASE=true must fail."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    env = {
        'EVENT_NAME': 'release',
        'RELEASE_TAG': 'v0.2.0',
        'IS_PRERELEASE': 'true',
        'RELEASE_REF': 'refs/tags/v0.2.0',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env)
    assert ret != 0
    assert 'Prereleases are not eligible for automated PyPI' in stderr


def test_non_dry_run_accepts_stable_release_and_invokes_gh_properly(
    tmp_path: Path,
) -> None:
    """Stable release query allows non-dry-run publishing to PyPI."""
    script = extract_validator_script()
    bin_dir = tmp_path / 'bin'
    log_file = tmp_path / 'gh.log'
    create_fake_gh(
        bin_dir,
        stdout=json.dumps({'isPrerelease': False}),
        log_file=log_file,
    )
    output_file = tmp_path / 'output.txt'

    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'RELEASE_TAG': 'v0.2.0',
        'DRY_RUN': 'false',
        'GITHUB_TOKEN': 'ghp_secret',
        'GITHUB_REPOSITORY': 'jordanestralioto/Global-Data-Finance',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, outputs = run_validator(
        script, env, custom_path=f'{bin_dir}:{os.environ.get("PATH", "")}'
    )
    assert ret == 0, stderr
    assert outputs['release_tag'] == 'v0.2.0'
    assert outputs['release_version'] == '0.2.0'
    assert outputs['dry_run'] == 'false'

    gh_call = log_file.read_text(encoding='utf-8').strip()
    expected_args = (
        'release view v0.2.0 --repo '
        'jordanestralioto/Global-Data-Finance --json isPrerelease'
    )
    assert gh_call == expected_args


def test_automated_release_event_succeeds_for_stable_release(
    tmp_path: Path,
) -> None:
    """Automated release event for stable release succeeds without dry_run."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    env = {
        'EVENT_NAME': 'release',
        'RELEASE_TAG': 'v0.2.0',
        'IS_PRERELEASE': 'false',
        'RELEASE_REF': 'refs/tags/v0.2.0',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, outputs = run_validator(script, env)
    assert ret == 0, stderr
    assert outputs['release_tag'] == 'v0.2.0'
    assert outputs['release_version'] == '0.2.0'
    assert outputs['dry_run'] == 'false'


def test_tag_syntax_validation_rejects_non_conforming_tags(
    tmp_path: Path,
) -> None:
    """Tags not strictly matching vMAJOR.MINOR.PATCH must fail."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'

    for invalid_tag in ('0.2.0', 'v0.2', 'v0.2.0-rc1', 'v1.0.0.0'):
        env = {
            'EVENT_NAME': 'workflow_dispatch',
            'RELEASE_TAG': invalid_tag,
            'DRY_RUN': 'true',
            'GITHUB_OUTPUT': str(output_file),
        }
        ret, stderr, _ = run_validator(script, env)
        assert ret != 0, f'Expected {invalid_tag} to fail'
        assert 'Publish requires a stable vMAJOR.MINOR.PATCH tag.' in stderr


def test_release_event_ref_mismatch_fails(tmp_path: Path) -> None:
    """If release ref does not match tag in release event, job must fail."""
    script = extract_validator_script()
    output_file = tmp_path / 'output.txt'
    env = {
        'EVENT_NAME': 'release',
        'RELEASE_TAG': 'v0.2.0',
        'IS_PRERELEASE': 'false',
        'RELEASE_REF': 'refs/tags/v0.1.9',
        'GITHUB_OUTPUT': str(output_file),
    }

    ret, stderr, _ = run_validator(script, env)
    assert ret != 0
    assert 'The published release ref must match its tag.' in stderr
