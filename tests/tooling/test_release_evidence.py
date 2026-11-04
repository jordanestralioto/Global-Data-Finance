"""Release evidence must reject missing executions and incomplete campaigns."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_release_evidence import (
    NATIVE_REQUIRED_CASES,
    verify_campaign,
    verify_native,
    verify_shards,
)
from tests.support.release_evidence import evaluate_results
from tests.support.release_fixtures import campaign_report, native_reports

pytestmark = pytest.mark.unit


def test_campaign_verifier_checks_complete_fault_dimensions() -> None:
    """An independently derived matrix covers partial and recovery failures."""
    report = campaign_report()

    assert verify_campaign(report) == 26
    assert 'partial:2:28:0.5' in report['cases']
    assert 'recovery-storage:1:persistent:0:5' in report['cases']


@pytest.mark.parametrize(
    'field',
    [
        'manifest',
        'cases',
        'expected',
        'attempted',
        'passed',
        'recovery_events',
        'initial_events',
        'status',
        'failures',
    ],
)
def test_campaign_verifier_rejects_incomplete_or_fabricated_evidence(
    field: str,
) -> None:
    """Counters alone cannot approve a partial or duplicated matrix."""
    report = campaign_report()
    if field in {'manifest', 'cases'}:
        report[field].pop()
    elif field in {'expected', 'attempted', 'passed'}:
        report[field] -= 1
    elif field == 'recovery_events':
        del report[field]['0']
    elif field == 'initial_events':
        report[field] = []
    elif field == 'status':
        report[field] = 'running'
    else:
        report[field] = ['injected failure']

    with pytest.raises(ValueError):
        verify_campaign(report)


def test_complete_scenario_set_requires_all_backup_and_destination_modes(
    tmp_path: Path,
) -> None:
    """A missing input/backup scenario blocks aggregate acceptance."""
    paths = []
    for existing in (False, True):
        for copy_backups in (False, True):
            path = tmp_path / f'{existing}-{copy_backups}.json'
            path.write_text(
                json.dumps(campaign_report(existing, copy_backups))
            )
            paths.append(path)

    assert verify_shards(paths, 1) == 104
    with pytest.raises(ValueError, match='every scenario'):
        verify_shards(paths[:-1], 1)
    with pytest.raises(ValueError, match='duplicated'):
        verify_shards(paths + paths[:1], 1)


def test_native_acceptance_requires_all_six_environments(
    tmp_path: Path,
) -> None:
    """A passing Linux run cannot substitute for native platform evidence."""
    paths = native_reports(tmp_path)

    assert verify_native(paths) == 6 * len(NATIVE_REQUIRED_CASES)
    with pytest.raises(ValueError, match='six environments'):
        verify_native(paths[:-1])


@pytest.mark.parametrize('outcome', ['skipped', 'failed', None])
def test_native_acceptance_rejects_skipped_failed_or_unexecuted_critical_cases(
    tmp_path: Path, outcome: str | None
) -> None:
    """Every collected critical parameter must genuinely execute and pass."""
    paths = native_reports(tmp_path)
    report = json.loads(paths[0].read_text())
    first = report['collected'][0]
    if outcome is None:
        del report['outcomes'][first]
    else:
        report['outcomes'][first] = outcome
    paths[0].write_text(json.dumps(report))

    with pytest.raises(ValueError):
        verify_native(paths)


@pytest.mark.parametrize(
    'collected,outcomes',
    [
        ([], {}),
        (['test_a'], {}),
        (['test_a'], {'test_a': 'skipped'}),
        (['test_a'], {'test_a': 'failed'}),
    ],
)
def test_release_results_reject_missing_successful_execution(
    collected: list[str], outcomes: dict[str, str]
) -> None:
    """Empty, unfinished, skipped, and failed suites are incomplete."""
    assert evaluate_results(collected, outcomes, [], [])
    assert evaluate_results(['test_a'], {'test_a': 'passed'}, ['test_b'], [])
    assert (
        evaluate_results(['test_a'], {'test_a': 'passed'}, ['test_a'], [])
        == []
    )
