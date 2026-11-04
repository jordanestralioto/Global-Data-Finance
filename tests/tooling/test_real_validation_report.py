"""Deterministic tests for real-validation report persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.real_validation_report import (
    REPORT_SCHEMA_VERSION,
    ReportFormatError,
    atomic_write,
    build_case_result,
    build_summary,
    read_json,
    read_results,
    redact,
    validate_status,
    write_json,
    write_results,
)
from scripts.real_validation_types import ValidationCase

pytestmark = pytest.mark.unit


def test_report_round_trip_is_sorted_and_secret_safe(tmp_path: Path) -> None:
    """JSON and JSONL persistence stays deterministic and redacted."""
    json_path = tmp_path / 'summary.json'
    results_path = tmp_path / 'results.jsonl'
    write_json(json_path, {'token': 'hidden', 'value': 1})
    write_results(
        results_path,
        {
            'case-b': {'caseId': 'case-b', 'status': 'passed'},
            'case-a': {'caseId': 'case-a', 'status': 'failed'},
        },
    )

    assert read_json(json_path) == {'token': '[REDACTED]', 'value': 1}
    lines = results_path.read_text(encoding='utf-8').splitlines()
    assert [json.loads(line)['caseId'] for line in lines] == [
        'case-a',
        'case-b',
    ]
    assert read_results(results_path)['case-a']['status'] == 'failed'


@pytest.mark.parametrize(
    'value',
    [b'not-json', b'[]', b'\xff'],
)
def test_read_json_rejects_invalid_or_non_object_evidence(
    tmp_path: Path, value: bytes
) -> None:
    """Malformed manifest and non-object JSON never enter the runner."""
    path = tmp_path / 'invalid.json'
    path.write_bytes(value)

    with pytest.raises(ReportFormatError):
        read_json(path)


@pytest.mark.parametrize(
    ('content', 'message'),
    [
        ('{bad}\n', 'invalid result JSON'),
        ('{"status":"passed"}\n', 'lacks a string caseId'),
        (
            '{"caseId":"same","status":"passed"}\n'
            '{"caseId":"same","status":"failed"}\n',
            'duplicate result',
        ),
    ],
)
def test_read_results_rejects_corrupt_or_duplicate_jsonl(
    tmp_path: Path, content: str, message: str
) -> None:
    """Result evidence must contain exactly one object per case ID."""
    path = tmp_path / 'results.jsonl'
    path.write_text(content, encoding='utf-8')

    with pytest.raises(ReportFormatError, match=message):
        read_results(path)


def test_read_results_missing_file_is_an_empty_result_set(
    tmp_path: Path,
) -> None:
    """A first campaign starts with no prior result lines."""
    assert read_results(tmp_path / 'missing.jsonl') == {}


def test_summary_counts_every_terminal_status_and_clamps_duration() -> None:
    """Summary totals distinguish all documented campaign states."""
    results: dict[str, dict[str, Any]] = {
        'passed': {
            'caseId': 'passed',
            'status': 'passed',
            'published': True,
        },
        'failed': {
            'caseId': 'failed',
            'status': 'failed',
            'published': True,
        },
        'skipped': {
            'caseId': 'skipped',
            'status': 'skipped',
            'published': None,
        },
        'external': {
            'caseId': 'external',
            'status': 'external_failure',
            'published': None,
        },
        'not-published': {
            'caseId': 'not-published',
            'status': 'not_published',
            'published': False,
        },
    }

    summary = build_summary(list(results), results, -1.0)

    assert summary['schemaVersion'] == REPORT_SCHEMA_VERSION
    assert summary['durationSeconds'] == 0.0
    assert summary['totalExecuted'] == 5
    assert summary['totalPublished'] == 2
    assert summary['statusCounts'] == {
        'passed': 1,
        'failed': 1,
        'skipped': 1,
        'external_failure': 1,
        'not_published': 1,
    }


def test_validate_status_accepts_all_states_and_rejects_unknown() -> None:
    """Only the five documented case statuses are serializable."""
    for status in (
        'passed',
        'failed',
        'skipped',
        'external_failure',
        'not_published',
    ):
        assert validate_status(status) == status
    with pytest.raises(ReportFormatError, match='invalid campaign status'):
        validate_status('unknown')


def test_redact_preserves_binary_values_and_normalizes_sequences() -> None:
    """Recursive redaction handles mapping keys, tuples, and bytes safely."""
    value = {1: ('token=hidden', b'binary')}

    assert redact(value) == {'1': ['token=[REDACTED]', b'binary']}


def test_atomic_write_removes_partial_file_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed atomic replacement leaves no hidden temporary report."""
    destination = tmp_path / 'summary.json'

    def fail_replace(_self: Path, target: Path) -> Path:
        raise OSError(f'cannot replace {target}')

    monkeypatch.setattr(Path, 'replace', fail_replace)

    with pytest.raises(OSError, match='cannot replace'):
        atomic_write(destination, '{}\n')

    assert list(tmp_path.iterdir()) == []


def test_build_case_result_returns_independent_complete_records(
    tmp_path: Path,
) -> None:
    """Case results contain 20 canonical keys with isolated containers."""
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path='https://example.test/dfp.zip',
        output_root=str(tmp_path / 'cvm-output'),
        document='DFP',
        mode='cvm',
        url='https://example.test/dfp.zip',
    )
    result_default = build_case_result(case)
    assert result_default['schemaVersion'] == REPORT_SCHEMA_VERSION
    assert result_default['caseId'] == 'cvm-DFP-2024'
    assert result_default['source'] == 'cvm'
    assert result_default['document'] == 'DFP'
    assert result_default['year'] == 2024
    assert result_default['inputPath'] == 'https://example.test/dfp.zip'
    assert result_default['inputSizeBytes'] is None
    assert result_default['inputSha256'] is None
    assert result_default['command'] == case.command()
    assert result_default['published'] is None
    assert result_default['publicResult'] is None
    assert result_default['artifactCount'] == 0
    assert result_default['artifacts'] == []
    assert result_default['recordCount'] == 0
    assert result_default['schema'] == {}
    assert result_default['temporaryFiles'] == []
    assert result_default['temporaryFilesAfterCleanup'] == []
    assert result_default['status'] == 'failed'
    assert result_default['message'] == 'case did not produce a result'
    assert result_default['durationSeconds'] == 0.0
    assert len(result_default) == 20

    result_custom = build_case_result(
        case, status='passed', message='completed normally'
    )
    assert result_custom['status'] == 'passed'
    assert result_custom['message'] == 'completed normally'

    result_default['artifacts'].append('file.parquet')
    result_default['schema']['col'] = 'int'
    result_default['temporaryFiles'].append('temp.tmp')
    result_default['temporaryFilesAfterCleanup'].append('leaked.tmp')

    assert result_custom['artifacts'] == []
    assert result_custom['schema'] == {}
    assert result_custom['temporaryFiles'] == []
    assert result_custom['temporaryFilesAfterCleanup'] == []
