"""Candidate acceptance binds every required result and distribution byte."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release_acceptance import (
    collect_acceptance,
    coverage_results,
    render_acceptance,
)
from tests.support.release_fixtures import acceptance_bundle

pytestmark = pytest.mark.integration
SHA = 'f' * 40
STATUSES = {'quality': 'success', 'security': 'success', 'package': 'success'}


def test_complete_candidate_evidence_renders_precise_automated_acceptance(
    tmp_path: Path,
) -> None:
    """Only a complete native, campaign, coverage, and package set passes."""
    acceptance_bundle(tmp_path, SHA)

    data = collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES)
    report = render_acceptance(data, 'https://example.test/runs/42')

    assert data['campaign_count'] == 192
    assert data['native_count'] > 0
    assert len(data['distributions']) == 2
    assert f'Candidate SHA: `{SHA}`' in report
    assert 'Automated prerequisites: passed' in report
    assert 'Review record:' not in report
    assert 'Independent general and security reviews: approved' not in report


@pytest.mark.parametrize('job', ['quality', 'security', 'package'])
@pytest.mark.parametrize('status', ['failure', 'skipped', 'cancelled', ''])
def test_missing_or_failed_prerequisite_job_cannot_authorize_publication(
    tmp_path: Path, job: str, status: str
) -> None:
    """An absent job never becomes success through aggregate evidence."""
    with pytest.raises(ValueError, match='prerequisites'):
        collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES | {job: status})


@pytest.mark.parametrize('kind', ['native', 'campaign', 'coverage'])
def test_evidence_from_another_candidate_is_rejected(
    tmp_path: Path, kind: str
) -> None:
    """Reusing a passing report from an older commit fails acceptance."""
    acceptance_bundle(tmp_path, SHA)
    prefixes = {
        'native': 'native-*',
        'campaign': 'publication-campaign-*',
        'coverage': 'coverage-report-*',
    }
    path = next(tmp_path.glob(prefixes[kind])) / 'environment.txt'
    path.write_text('a' * 40 + '\n')

    with pytest.raises(ValueError, match='candidate SHA'):
        collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES)


def test_changed_distribution_bytes_cannot_reuse_checked_metadata(
    tmp_path: Path,
) -> None:
    """The distribution downloaded for publishing must match its digest."""
    acceptance_bundle(tmp_path, SHA)
    wheel = next((tmp_path / 'dist-packages').glob('*.whl'))
    with wheel.open('ab') as handle:
        handle.write(b'different bytes after inspection')

    with pytest.raises(ValueError, match='distribution bytes'):
        collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES)


@pytest.mark.parametrize('percentage', [84.9, float('nan'), float('inf')])
def test_coverage_floor_rejects_low_and_nonfinite_values(
    tmp_path: Path, percentage: float
) -> None:
    """Malformed JSON numeric values cannot bypass the coverage floor."""
    acceptance_bundle(tmp_path, SHA)
    path = tmp_path / 'coverage-report-py3.13' / 'executor.json'
    report = json.loads(path.read_text())
    report['totals']['percent_covered'] = percentage
    path.write_text(json.dumps(report))

    with pytest.raises(ValueError, match='coverage below'):
        coverage_results(tmp_path, SHA)


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_missing_installed_distribution_execution_is_rejected(
    tmp_path: Path, kind: str
) -> None:
    """A successful build alone cannot substitute for isolated smoke flows."""
    acceptance_bundle(tmp_path, SHA)
    (tmp_path / 'release-package-evidence' / f'smoke-{kind}.status').unlink()

    with pytest.raises(OSError):
        collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES)


def test_release_acceptance_does_not_require_planning_or_review_files(
    tmp_path: Path,
) -> None:
    """Complete CI evidence passes without repository planning documents."""
    acceptance_bundle(tmp_path, SHA)

    data = collect_acceptance(tmp_path, '0.2.0', SHA, STATUSES)

    assert not (tmp_path / 'plans').exists()
    assert not (tmp_path / 'repository').exists()
    assert data['version'] == '0.2.0'
    assert data['sha'] == SHA
    assert data['campaign_count'] == 192
    assert data['native_count'] > 0
    assert set(data['coverage']) == {'3.12', '3.13', '3.14'}
