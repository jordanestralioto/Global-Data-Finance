"""Release workflow wiring and tag selection enforce required evidence."""

from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path

import pytest

from scripts.process_runner import run_process

pytestmark = pytest.mark.integration
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (REPOSITORY_ROOT / '.github' / 'workflows' / name).read_text()


def _job(content: str, name: str) -> str:
    match = re.search(
        rf'(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)', content
    )
    assert match is not None, f'job missing: {name}'
    return match[1]


def test_native_matrix_requires_real_tests_and_retained_artifacts() -> None:
    """Six native environments must enforce critical execution outcomes."""
    native = _job(_workflow('pipeline.yml'), 'native-regressions')

    assert 'os: [windows-latest, macos-latest]' in native
    assert 'python: ["3.12", "3.13", "3.14"]' in native
    assert '-p tests.support.release_evidence --release-native' in native
    assert '--release-evidence=' in native and '--junitxml=' in native
    assert 'test_transaction_recovery.py' in native
    assert 'tests/application/b3_docs/test_release_regressions.py' in native
    assert 'retention-days: 30' in native
    assert 'continue-on-error' not in native
    assert 'ref: ${{ github.sha }}' in native


def test_complete_campaign_is_required_for_release_and_manual_validation() -> (
    None
):
    """All eight shards and aggregate trace verification gate releases."""
    workflow = _workflow('pipeline.yml')
    campaign = _job(workflow, 'publication-fault-campaign')
    aggregate = _job(workflow, 'verify-publication-campaign')

    assert "inputs.release_tag != ''" in campaign
    assert "github.event_name == 'workflow_dispatch'" in campaign
    assert 'max-parallel: 2' in campaign
    assert 'shard: [0, 1, 2, 3, 4, 5, 6, 7]' in campaign
    assert "-m 'integration and slow'" in campaign
    assert 'tests/macro_infra/test_publication_fault_campaign.py' in campaign
    assert 'needs: publication-fault-campaign' in aggregate
    assert 'scripts/check_release_evidence.py' in aggregate
    assert '--shards 8' in aggregate
    assert 'continue-on-error' not in campaign + aggregate


def test_publish_requires_acceptance_before_trusted_publication() -> None:
    """A build cannot bypass native, coverage, or campaign evidence."""
    workflow = _workflow('publish.yml')
    publish = _job(workflow, 'publish')
    acceptance = _job(workflow, 'release-acceptance')
    needs = set(re.findall(r'^      - ([a-z-]+)$', publish, re.M))

    assert {
        'validate-release-tag',
        'security-scan',
        'quality',
        'package-check',
        'release-acceptance',
    } <= needs
    assert "needs.validate-release-tag.outputs.dry_run != 'true'" in publish
    assert 'id-token: write' in publish
    assert 'id-token' not in acceptance
    assert 'scripts.release_acceptance' in acceptance
    assert 'if: always()' in acceptance
    assert '--sha "$RELEASE_SHA"' in acceptance
    assert '--quality-status "$QUALITY_STATUS"' in acceptance
    assert '--security-status "$SECURITY_STATUS"' in acceptance
    assert '--package-status "$PACKAGE_STATUS"' in acceptance
    assert 'name: dist-packages' in publish
    assert 'uv build' not in publish


def test_package_checks_install_both_formats_outside_source_tree() -> None:
    """Both installed distributions exercise real source flows."""
    package = _job(_workflow('publish.yml'), 'package-check')

    assert 'scripts.check_distributions' in package
    assert 'dist/*.whl' in package and 'dist/*.tar.gz' in package
    assert 'uv venv "$gdf_package_environment"' in package
    assert 'cd "$RUNNER_TEMP"' in package
    assert '"$gdf_package_environment/bin/python" -I' in package
    assert 'tests/support/package_smoke.py' in package
    assert 'cp -R "$RUNNER_TEMP/package-fixtures" "$gdf_package_inputs"' in (
        package
    )
    assert 'check "$gdf_package_inputs"' in package
    assert '"$gdf_smoke_prefix-$gdf_distribution_kind.status"' in package
    assert 'retention-days: 30' in package


def _release_range_script() -> str:
    content = _workflow('pipeline.yml')
    step = content.split('      - name: Select release change range\n', 1)[1]
    match = re.search(r'(?m)^        run: \|\n((?:          .*\n)+)', step)
    assert match is not None
    return textwrap.dedent(match[1])


@pytest.mark.parametrize('matching', [False, True])
def test_release_range_rejects_tag_pointing_to_another_commit(
    tmp_path: Path, matching: bool
) -> None:
    """Execute the actual CI shell selection against a temporary Git repo."""

    def git(*arguments: str) -> str:
        return run_process(['git', *arguments], cwd=tmp_path).stdout.strip()

    git('init')
    git('config', 'user.name', 'Release Test')
    git('config', 'user.email', 'release@example.test')
    source = tmp_path / 'source.txt'
    source.write_text('old')
    git('add', 'source.txt')
    git('commit', '-m', 'Initial fixture')
    git('tag', 'v0.1.0')
    source.write_text('candidate')
    git('commit', '-am', 'Candidate fixture')
    git('tag', 'v0.2.0')
    candidate = git('rev-parse', 'HEAD')
    source.write_text('later')
    git('commit', '-am', 'Later fixture')
    head = candidate if matching else git('rev-parse', 'HEAD')
    output = tmp_path / 'github-env.txt'

    result = run_process(
        ['bash', '-e', '-c', _release_range_script()],
        cwd=tmp_path,
        check=False,
        env={
            'PATH': os.environ.get('PATH', ''),
            'RELEASE_TAG': 'v0.2.0',
            'QUALITY_GATE_HEAD': head,
            'GITHUB_ENV': str(output),
        },
    )

    if matching:
        assert result.returncode == 0, result.stderr
        assert (
            output.read_text().strip()
            == f'QUALITY_GATE_RANGE=v0.1.0...{candidate}'
        )
    else:
        assert result.returncode != 0
        assert 'does not identify the workflow SHA' in result.stderr
        assert not output.exists()
