"""Exercise validation report transport with actual spawned workers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psutil
import pytest

from scripts import real_validation_runner as runner
from scripts.real_validation_b3 import execute_cotahist_case
from scripts.real_validation_matrix import build_cases, manifest_for
from scripts.real_validation_report import write_json
from scripts.real_validation_resume import resume_cases
from scripts.real_validation_types import ValidationCase
from scripts.real_validation_utils import sha256_file
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.integration


@pytest.fixture
def stable_memory_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tiny corpus checks independent of host memory pressure."""
    memory = SimpleNamespace(
        total=8 * 1024**3,
        available=6 * 1024**3,
        percent=25.0,
    )
    monkeypatch.setattr(psutil, 'virtual_memory', lambda: memory)


def _large_report_worker(
    case: ValidationCase,
    timeout: float,
    workspace: Path,
    log_path: Path,
    result_queue: Any,
) -> None:
    """Publish evidence larger than the process queue pipe buffer."""
    del timeout, workspace, log_path
    result_queue.put(runner.control_result(case, 'passed', 'x' * 1_048_576))


def test_spawned_worker_delivers_large_report_before_process_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Large evidence arrives intact without a false execution timeout."""
    case = ValidationCase(
        case_id='cotahist-large-report',
        source='cotahist',
        year=2024,
        input_path=str(tmp_path / 'COTAHIST_A2024.ZIP'),
        output_root='',
        mode='fast',
    )
    monkeypatch.setattr(runner, 'case_worker', _large_report_worker)

    result = runner.run_isolated_case(tmp_path / 'report', case, timeout=5)

    assert result['status'] == 'passed'
    assert result['message'] == 'x' * 1_048_576
    assert result['temporaryFilesAfterCleanup'] == []
    assert runner.process_check() == {
        'status': 'passed',
        'activeProcesses': [],
    }


def _alternative_full_range_case(tmp_path: Path) -> ValidationCase:
    sources = tmp_path / 'sources'
    sources.mkdir()
    for year in range(2000, 2027):
        write_cotahist_zip(
            sources,
            year=year,
            records=[build_cotahist_record(year=year)],
        )
    cases = build_cases(
        source='cotahist',
        initial_year=2000,
        last_year=2026,
        document=None,
        cotahist_path=str(sources),
        cvm_output=None,
        cotahist_modes='all',
    )
    return next(case for case in cases if case.mode == 'multi_parity')


@pytest.mark.usefixtures('stable_memory_snapshot')
def test_generic_full_range_accepts_alternative_corpus_and_symlink_workspace(
    tmp_path: Path,
) -> None:
    """Native reconciliation proves both modes against caller snapshots."""
    case = _alternative_full_range_case(tmp_path)
    physical = tmp_path / 'physical-work'
    physical.mkdir()
    alias = tmp_path / 'alias-work'
    alias.symlink_to(physical, target_is_directory=True)

    result = execute_cotahist_case(case, alias / 'case')

    assert result['status'] == 'passed', result['message']
    assert result['recordCount'] == 27
    assert result['rawReconciliation']['rawQuotes'] == 27
    assert result['rawReconciliation']['verifiedRows'] == 27
    assert result['modeParity'] == 'exact ordered rows'
    assert result['artifactCount'] == 2
    assert all(
        result['publicResult'][mode]['success'] for mode in ('fast', 'slow')
    )


@pytest.mark.usefixtures('stable_memory_snapshot')
def test_explicit_historical_acceptance_rejects_alternative_source_bytes(
    tmp_path: Path,
) -> None:
    """Opting into history retains its strict source checksum rejection."""
    case = replace(
        _alternative_full_range_case(tmp_path), frozen_baseline=True
    )

    result = execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'failed'
    assert (
        'frozen COTAHIST source checksum manifest differs' in result['message']
    )


@pytest.mark.parametrize('historical', [False, True])
def test_resume_preserves_explicit_historical_baseline_selection(
    tmp_path: Path, historical: bool
) -> None:
    """Manifest round trips cannot silently change acceptance intent."""
    case = replace(
        _alternative_full_range_case(tmp_path), frozen_baseline=historical
    )
    report = tmp_path / 'report'
    report.mkdir()
    manifest = manifest_for(
        [case],
        source='cotahist',
        initial_year=2000,
        last_year=2026,
        document=None,
        cotahist_path=str(Path(case.input_path).parent),
        cvm_output=None,
        timeout=300,
    )
    write_json(report / 'manifest.json', manifest)

    resumed = resume_cases(report, hash_file=sha256_file)

    assert resumed == [case]
    assert resumed[0].frozen_baseline is historical
    assert manifest['campaign']['cotahistFrozenBaseline'] is historical
    assert (
        'historical_frozen_baseline=True' in resumed[0].command()
    ) is historical
