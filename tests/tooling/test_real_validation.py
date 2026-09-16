"""Tests for the opt-in real-validation campaign contracts."""

from __future__ import annotations

import importlib
import json
import re
import shlex
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.real_validation as cli
import scripts.real_validation_runner as runner
from globaldatafinance.macro_exceptions import SecurityError
from scripts.real_validation import (
    _filter_cases,
    _positive_timeout,
    _required_source,
    _validate_case_output_roots,
    _validate_external_directory,
    _validate_optional_external_directory,
    _validate_report_path,
    main,
)
from scripts.real_validation_b3 import _canonical_digest
from scripts.real_validation_matrix import (
    CVM_DOCUMENT_WINDOWS,
    build_cases,
)
from scripts.real_validation_report import (
    ReportFormatError,
    build_summary,
    redact,
    write_json,
    write_results,
)
from scripts.real_validation_runner import resume_cases
from scripts.real_validation_types import ValidationCase
from scripts.real_validation_utils import sha256_file, temporary_paths
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_zip,
    write_zip,
)

pytestmark = pytest.mark.unit


_REAL_VALIDATION_HOOK_ID = 'real-validation-coverage'
_REAL_VALIDATION_CI_STEP_NAME = 'Run real-validation executor coverage'
_REAL_VALIDATION_TEST_TOKEN = re.compile(
    r'tests/tooling/test_real_validation[^/]*\.py\Z'
)
_REAL_VALIDATION_COVERAGE_TOKEN = re.compile(
    r'--cov=scripts\.real_validation\w*\Z'
)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML mapping for structural configuration assertions."""
    yaml_module = importlib.import_module('yaml')
    payload = yaml_module.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise AssertionError(f'{path} must contain a YAML mapping')
    return cast(dict[str, Any], payload)


def _extract_real_validation_targets(
    command: str,
) -> tuple[list[str], list[str]]:
    """Return executor test paths and coverage modules from one command."""
    tokens = shlex.split(command, comments=True, posix=True)
    test_paths = [
        token
        for token in tokens
        if _REAL_VALIDATION_TEST_TOKEN.fullmatch(token)
    ]
    coverage_modules = [
        token.removeprefix('--cov=')
        for token in tokens
        if _REAL_VALIDATION_COVERAGE_TOKEN.fullmatch(token)
    ]
    return test_paths, coverage_modules


def _assert_unique_structural_command(
    selected_command: str,
    commands: list[str],
    config_label: str,
) -> None:
    """Require one selected command to own all executor targets."""
    targeted_commands = [
        command
        for command in commands
        if any(_extract_real_validation_targets(command))
    ]
    assert targeted_commands == [selected_command], (
        f'{config_label} must contain exactly one command with '
        'real-validation targets'
    )


def _assert_real_validation_command(
    command: str,
    expected_test_paths: list[str],
    expected_coverage_modules: list[str],
    config_label: str,
) -> None:
    """Validate ordered, unique executor arguments in one command."""
    configured_test_paths, configured_coverage_modules = (
        _extract_real_validation_targets(command)
    )

    assert len(configured_test_paths) == len(set(configured_test_paths)), (
        f'{config_label} contains duplicate executor test paths'
    )
    assert len(configured_coverage_modules) == len(
        set(configured_coverage_modules)
    ), f'{config_label} contains duplicate executor coverage modules'
    assert configured_test_paths == expected_test_paths, (
        f'{config_label} has a stale or reordered real-validation test list'
    )
    assert configured_coverage_modules == expected_coverage_modules, (
        f'{config_label} has a stale or reordered '
        'real-validation coverage list'
    )


def _find_precommit_real_validation_command(
    config: dict[str, Any],
) -> tuple[str, list[str]]:
    """Find the executor hook and all parsed hook entries."""
    repositories = config.get('repos')
    assert isinstance(repositories, list)
    matching_hooks: list[dict[str, Any]] = []
    commands: list[str] = []

    for repository in repositories:
        assert isinstance(repository, dict)
        hooks = repository.get('hooks', [])
        assert isinstance(hooks, list)
        for hook in hooks:
            assert isinstance(hook, dict)
            entry = hook.get('entry')
            arguments = hook.get('args', [])
            assert isinstance(arguments, list)
            command_parts = [entry] if isinstance(entry, str) else []
            command_parts.extend(str(argument) for argument in arguments)
            if command_parts:
                commands.append(' '.join(command_parts))
            if hook.get('id') == _REAL_VALIDATION_HOOK_ID:
                matching_hooks.append(cast(dict[str, Any], hook))

    assert len(matching_hooks) == 1
    entry = matching_hooks[0].get('entry')
    assert isinstance(entry, str)
    arguments = matching_hooks[0].get('args', [])
    assert isinstance(arguments, list)
    return ' '.join(
        [entry, *(str(argument) for argument in arguments)]
    ), commands


def _find_ci_real_validation_command(
    config: dict[str, Any],
) -> tuple[str, list[str]]:
    """Find the executor step and all run commands in the quality job."""
    jobs = config.get('jobs')
    assert isinstance(jobs, dict)
    quality_job = jobs.get('quality')
    assert isinstance(quality_job, dict)
    steps = quality_job.get('steps')
    assert isinstance(steps, list)
    matching_steps: list[dict[str, Any]] = []
    commands: list[str] = []

    for job_name, job in jobs.items():
        assert isinstance(job, dict)
        job_steps = job.get('steps', [])
        assert isinstance(job_steps, list)
        for step in job_steps:
            assert isinstance(step, dict)
            run = step.get('run')
            if isinstance(run, str):
                commands.append(run)
            if (
                job_name == 'quality'
                and step.get('name') == _REAL_VALIDATION_CI_STEP_NAME
            ):
                matching_steps.append(cast(dict[str, Any], step))

    assert len(matching_steps) == 1
    run = matching_steps[0].get('run')
    assert isinstance(run, str)
    return run, commands


def test_cvm_matrix_covers_all_document_windows(tmp_path: Path) -> None:
    """The default CVM matrix contains exactly the seven valid windows."""
    cases = build_cases(
        source='cvm',
        initial_year=None,
        last_year=None,
        document=None,
        cotahist_path=None,
        cvm_output=str(tmp_path),
    )

    counts = {
        document: sum(case.document == document for case in cases)
        for document in CVM_DOCUMENT_WINDOWS
    }
    assert len(cases) == 102
    assert counts == {
        document: last_year - first_year + 1
        for document, (first_year, last_year) in CVM_DOCUMENT_WINDOWS.items()
    }
    assert all(case.input_path == case.url for case in cases)


def test_real_validation_coverage_contract_matches_executor_surface() -> None:
    """The dedicated hook and CI gate cover every executor module and test."""
    repository_root = Path(__file__).resolve().parents[2]
    script_modules = sorted(
        path.stem
        for path in (repository_root / 'scripts').glob('real_validation*.py')
    )
    test_modules = sorted(
        path.stem.removeprefix('test_')
        for path in (repository_root / 'tests' / 'tooling').glob(
            'test_real_validation*.py'
        )
    )

    assert script_modules
    assert test_modules == script_modules

    expected_coverage_modules = [
        f'scripts.{module}' for module in script_modules
    ]
    expected_test_paths = [
        f'tests/tooling/test_{module}.py' for module in script_modules
    ]

    precommit_command, precommit_commands = (
        _find_precommit_real_validation_command(
            _load_yaml_mapping(repository_root / '.pre-commit-config.yaml')
        )
    )
    _assert_unique_structural_command(
        precommit_command,
        precommit_commands,
        '.pre-commit-config.yaml',
    )
    _assert_real_validation_command(
        precommit_command,
        expected_test_paths,
        expected_coverage_modules,
        '.pre-commit-config.yaml',
    )

    ci_command, ci_commands = _find_ci_real_validation_command(
        _load_yaml_mapping(
            repository_root / '.github' / 'workflows' / 'pipeline.yml'
        )
    )
    _assert_unique_structural_command(
        ci_command,
        ci_commands,
        '.github/workflows/pipeline.yml',
    )
    _assert_real_validation_command(
        ci_command,
        expected_test_paths,
        expected_coverage_modules,
        '.github/workflows/pipeline.yml',
    )


@pytest.mark.parametrize(
    ('command', 'message'),
    [
        (
            'pytest tests/tooling/test_real_validation.py '
            'tests/tooling/test_real_validation.py '
            '--cov=scripts.real_validation',
            'duplicate executor test paths',
        ),
        (
            'pytest tests/tooling/test_real_validation.py '
            '--cov=scripts.real_validation --cov=scripts.real_validation',
            'duplicate executor coverage modules',
        ),
    ],
)
def test_real_validation_command_contract_rejects_duplicate_targets(
    command: str, message: str
) -> None:
    """The contract fails closed when a command repeats an executor target."""
    with pytest.raises(AssertionError, match=message):
        _assert_real_validation_command(
            command,
            ['tests/tooling/test_real_validation.py'],
            ['scripts.real_validation'],
            'synthetic command',
        )


def test_real_validation_structure_rejects_targets_in_multiple_commands() -> (
    None
):
    """The structural contract rejects executor targets outside its command."""
    selected_command = (
        'pytest tests/tooling/test_real_validation.py '
        '--cov=scripts.real_validation'
    )
    other_command = (
        'pytest tests/tooling/test_real_validation_b3.py '
        '--cov=scripts.real_validation_b3'
    )

    with pytest.raises(AssertionError, match='exactly one command'):
        _assert_unique_structural_command(
            selected_command,
            [selected_command, other_command],
            'synthetic configuration',
        )


def test_real_validation_target_parser_ignores_shell_comments() -> None:
    """Commented examples cannot be mistaken for configured targets."""
    command = (
        'pytest tests/tooling/test_real_validation.py '
        '--cov=scripts.real_validation '
        '# tests/tooling/test_real_validation_b3.py '
        '--cov=scripts.real_validation_b3'
    )

    assert _extract_real_validation_targets(command) == (
        ['tests/tooling/test_real_validation.py'],
        ['scripts.real_validation'],
    )


def test_cvm_matrix_clamps_requested_years_to_document_window(
    tmp_path: Path,
) -> None:
    """A narrowed request cannot create cases outside a document window."""
    cases = build_cases(
        source='cvm',
        initial_year=2010,
        last_year=2018,
        document='ITR',
        cotahist_path=None,
        cvm_output=str(tmp_path),
    )

    assert [case.year for case in cases] == list(range(2011, 2019))
    assert {case.document for case in cases} == {'ITR'}


def test_manifest_command_describes_public_parity_operations() -> None:
    """Manifest evidence names both public B3 modes for a parity case."""
    case = ValidationCase(
        case_id='cotahist-parity-2024',
        source='cotahist',
        year=2024,
        input_path='/data/COTAHIST_A2024.ZIP',
        output_root='',
        mode='parity',
    )

    assert case.command() == [
        'HistoricalQuotesB3.extract_async',
        'path_of_docs=/data',
        'assets_list=[ações]',
        'initial_year=2024',
        'last_year=2024',
        'processing_mode=fast+slow',
        'automatic_network_access=False',
    ]


def test_summary_counts_only_cases_from_the_current_manifest() -> None:
    """Retries and stale result lines cannot inflate the campaign totals."""
    results: dict[str, dict[str, Any]] = {
        'case-a': {'caseId': 'case-a', 'status': 'passed', 'published': True},
        'case-b': {
            'caseId': 'case-b',
            'status': 'external_failure',
            'published': None,
        },
        'stale': {'caseId': 'stale', 'status': 'failed', 'published': True},
    }

    summary = build_summary(['case-a', 'case-b', 'case-c'], results, 1.25)

    assert summary['totalCombinations'] == 3
    assert summary['totalExecuted'] == 2
    assert summary['totalNotExecuted'] == 1
    assert summary['totalPublished'] == 1
    assert summary['statusCounts']['passed'] == 1
    assert summary['statusCounts']['external_failure'] == 1
    assert summary['statusCounts']['failed'] == 0
    assert summary['unclassifiedCaseIds'] == ['case-c']


def test_report_redacts_credential_shaped_values_recursively(
    tmp_path: Path,
) -> None:
    """Evidence serialization does not retain common credential values."""
    report_path = tmp_path / 'summary.json'
    write_json(
        report_path,
        {
            'message': 'token=secret-value',
            'nested': ['authorization: Bearer another-secret'],
        },
    )
    payload = json.loads(report_path.read_text(encoding='utf-8'))

    assert redact({'token': 'secret'}) == {'token': '[REDACTED]'}
    assert '[REDACTED]' in payload['message']
    assert '[REDACTED]' in payload['nested'][0]
    assert 'secret-value' not in report_path.read_text(encoding='utf-8')


def test_cotahist_digest_is_order_independent(tmp_path: Path) -> None:
    """The bounded fallback digest ignores incidental processing order."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    pq.write_table(pa.table({'ticker': ['B', 'A'], 'value': [2, 1]}), first)
    pq.write_table(pa.table({'ticker': ['A', 'B'], 'value': [1, 2]}), second)

    assert _canonical_digest(first) == _canonical_digest(second)


def test_temporary_paths_detect_tmp_suffix(tmp_path: Path) -> None:
    """Validation evidence includes hidden append and merge temporary files."""
    temporary = tmp_path / 'cotahist.parquet.tmp'
    temporary.touch()

    assert temporary_paths(tmp_path) == ['cotahist.parquet.tmp']


def test_cli_rejects_missing_cotahist_dataset_before_manifest_creation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing explicit dataset is an immediate functional CLI failure."""
    report_path = tmp_path / 'report'
    exit_code = main(
        [
            '--source',
            'cotahist',
            '--cotahist-path',
            str(tmp_path / 'missing'),
            '--report',
            str(report_path),
        ]
    )
    error = capsys.readouterr().err

    assert exit_code == 3
    assert 'COTAHIST directory does not exist' in error
    assert not (report_path / 'manifest.json').exists()


@pytest.mark.parametrize(
    'raw_path',
    [
        '/',
        '/etc',
        'C:\\',
        r'C:relative',
        r'\Windows',
        r'\\server\share\output',
    ],
)
def test_cli_destination_policy_rejects_privileged_and_untrusted_paths(
    raw_path: str,
) -> None:
    """CLI destinations use the shared POSIX, drive, and UNC policy."""
    with pytest.raises(SecurityError, match='Security violation'):
        _validate_external_directory(raw_path, 'destination')


def test_cli_destination_policy_allows_tmp_without_creating_it() -> None:
    """The external scratch root is allowed without being touched."""
    tmp_root = Path('/', 'tmp')
    assert _validate_external_directory(str(tmp_root), 'destination') == (
        tmp_root
    )


def test_cli_security_error_is_a_deterministic_configuration_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rejected CVM destination cannot create a report or workspace."""
    report_path = tmp_path / 'report'
    exit_code = main(
        [
            '--source',
            'cvm',
            '--cvm-output',
            '/etc',
            '--report',
            str(report_path),
        ]
    )
    payload = json.loads(capsys.readouterr().err)

    assert exit_code == 3
    assert payload == {
        'code': 'invalid_campaign',
        'message': payload['message'],
        'schemaVersion': 1,
    }
    assert 'Security violation' in payload['message']
    assert not report_path.exists()


def test_cli_report_policy_rejects_before_any_manifest_or_output_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rejected report path stops execution before CVM output setup."""
    output_path = tmp_path / 'cvm-output'
    exit_code = main(
        [
            '--source',
            'cvm',
            '--cvm-output',
            str(output_path),
            '--report',
            '/etc',
        ]
    )

    assert exit_code == 3
    assert 'Security violation' in capsys.readouterr().err
    assert not output_path.exists()


def _cotahist_case(
    archive: Path, *, case_id: str = 'cotahist-fast-2024'
) -> ValidationCase:
    """Build a manifest case with the current archive evidence."""
    return ValidationCase(
        case_id=case_id,
        source='cotahist',
        year=2024,
        input_path=str(archive),
        output_root='',
        mode='fast',
        input_size_bytes=archive.stat().st_size,
        input_sha256=sha256_file(archive),
    )


def _write_resume_manifest(
    report_path: Path, cases: list[ValidationCase]
) -> None:
    """Write the smallest valid manifest needed by resume tests."""
    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 1,
            'cases': [case.to_manifest_dict() for case in cases],
        },
    )


def test_resume_accepts_identical_hashes_and_hashes_shared_input_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matching evidence permits resume and deduplicates shared hashing."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    fast = _cotahist_case(archive)
    parity = replace(
        fast,
        case_id='cotahist-parity-2024',
        mode='parity',
    )
    report_path = tmp_path / 'report'
    _write_resume_manifest(report_path, [fast, parity])
    calls: list[Path] = []
    original_hash = runner.sha256_file

    def counting_hash(path: Path) -> str:
        calls.append(path)
        return original_hash(path)

    monkeypatch.setattr(runner, 'sha256_file', counting_hash)

    resumed = resume_cases(report_path)

    assert [case.case_id for case in resumed] == [
        'cotahist-fast-2024',
        'cotahist-parity-2024',
    ]
    assert calls == [archive.resolve()]


def test_resume_rejects_removed_input_with_case_and_new_campaign_guidance(
    tmp_path: Path,
) -> None:
    """A removed input is a report-format failure before execution."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    write_cotahist_zip(
        tmp_path,
        year=2023,
        records=[build_cotahist_record(year=2023)],
    )
    case = _cotahist_case(archive)
    report_path = tmp_path / 'report'
    _write_resume_manifest(report_path, [case])
    archive.unlink()

    with pytest.raises(ReportFormatError) as error:
        resume_cases(report_path)

    message = str(error.value)
    assert 'caseId=cotahist-fast-2024' in message
    assert 'missing' in message
    assert 'Start a new campaign' in message


def test_resume_rejects_changed_input_size_without_touching_old_results(
    tmp_path: Path,
) -> None:
    """A valid replacement with a different size cannot overwrite evidence."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    case = _cotahist_case(archive)
    report_path = tmp_path / 'report'
    _write_resume_manifest(report_path, [case])
    results_path = report_path / 'results.jsonl'
    write_results(
        results_path,
        {'cotahist-fast-2024': {'caseId': case.case_id, 'status': 'passed'}},
    )
    original_results = results_path.read_text(encoding='utf-8')
    write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024),
            build_cotahist_record(year=2024, ticker='VALE3'),
        ],
    )

    with pytest.raises(ReportFormatError, match='input_size_bytes'):
        resume_cases(report_path)

    assert results_path.read_text(encoding='utf-8') == original_results


def test_cli_resume_rejects_drift_before_running_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI resume stops before the runner can execute or rewrite evidence."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    case = _cotahist_case(archive)
    report_path = tmp_path / 'report'
    _write_resume_manifest(report_path, [case])
    results_path = report_path / 'results.jsonl'
    write_results(
        results_path,
        {'cotahist-fast-2024': {'caseId': case.case_id, 'status': 'passed'}},
    )
    original_results = results_path.read_text(encoding='utf-8')
    write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024),
            build_cotahist_record(year=2024, ticker='VALE3'),
        ],
    )
    called = False

    def fail_if_called(*_args: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(cli, 'run_campaign', fail_if_called)

    assert main(['--resume', '--report', str(report_path)]) == 3
    assert 'Start a new campaign' in capsys.readouterr().err
    assert called is False
    assert results_path.read_text(encoding='utf-8') == original_results


def test_resume_rejects_same_size_replacement_with_different_hash(
    tmp_path: Path,
) -> None:
    """A same-size valid replacement is rejected by its content hash."""
    archive = tmp_path / 'COTAHIST_A2024.ZIP'
    write_zip(
        archive,
        {
            'COTAHIST_A2024.TXT': build_cotahist_record(
                year=2024, ticker='PETR4'
            ).encode('latin-1')
        },
        compression=zipfile.ZIP_STORED,
    )
    case = _cotahist_case(archive)
    report_path = tmp_path / 'report'
    _write_resume_manifest(report_path, [case])
    original_size = archive.stat().st_size
    write_zip(
        archive,
        {
            'COTAHIST_A2024.TXT': build_cotahist_record(
                year=2024, ticker='VALE3'
            ).encode('latin-1')
        },
        compression=zipfile.ZIP_STORED,
    )

    assert archive.stat().st_size == original_size
    with pytest.raises(ReportFormatError, match='input_sha256'):
        resume_cases(report_path)


def test_cli_builds_manifest_only_after_validating_external_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid initial request writes its manifest and delegates execution."""
    report_path = tmp_path / 'report'
    output_path = tmp_path / 'cvm-output'
    calls: list[tuple[Path, list[ValidationCase], float]] = []

    def fake_run(
        report: Path, cases: list[ValidationCase], timeout: float
    ) -> int:
        calls.append((report, cases, timeout))
        return 0

    monkeypatch.setattr(cli, 'run_campaign', fake_run)

    exit_code = main(
        [
            '--source',
            'cvm',
            '--document',
            'DFP',
            '--initial-year',
            '2024',
            '--last-year',
            '2024',
            '--cvm-output',
            str(output_path),
            '--report',
            str(report_path),
            '--timeout',
            '5',
        ]
    )
    manifest = json.loads(
        (report_path / 'manifest.json').read_text(encoding='utf-8')
    )

    assert exit_code == 0
    assert calls[0][0] == report_path.resolve()
    assert [case.case_id for case in calls[0][1]] == ['cvm-DFP-2024']
    assert calls[0][2] == 5.0
    assert manifest['cases'][0]['outputRoot'] == str(output_path.resolve())


def test_cli_resume_validates_manifest_output_before_delegating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resume validates the persisted campaign destination before running."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    output_path = tmp_path / 'cvm-output'
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        'dfp_cia_aberta_2024.zip'
    )
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=str(output_path),
        document='DFP',
        mode='cvm',
        url=url,
    )
    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 1,
            'campaign': {'cvmOutput': str(output_path)},
            'cases': [case.to_manifest_dict()],
        },
    )
    called = False

    def fake_run(*_args: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(cli, 'run_campaign', fake_run)

    assert main(['--resume', '--report', str(report_path)]) == 0
    assert called is True


def test_cli_resume_rejects_tampered_cvm_output_root_before_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI resume rejects a case destination changed after the campaign."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    trusted_output = tmp_path / 'trusted-output'
    attacker_output = tmp_path / 'attacker-output'
    url = (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        'dfp_cia_aberta_2024.zip'
    )
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path=url,
        output_root=str(attacker_output),
        document='DFP',
        mode='cvm',
        url=url,
    )
    write_json(
        report_path / 'manifest.json',
        {
            'schemaVersion': 1,
            'campaign': {'cvmOutput': str(trusted_output)},
            'cases': [case.to_manifest_dict()],
        },
    )
    called = False

    def fail_if_called(*_args: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(cli, 'run_campaign', fail_if_called)

    assert main(['--resume', '--report', str(report_path)]) == 3
    assert 'outputRoot' in capsys.readouterr().err
    assert called is False
    assert not trusted_output.exists()
    assert not attacker_output.exists()


def test_cli_validation_helpers_reject_invalid_inputs_and_filter_cases(
    tmp_path: Path,
) -> None:
    """CLI helper failures are deterministic and case IDs are exact."""
    file_path = tmp_path / 'not-a-directory'
    file_path.write_text('x', encoding='utf-8')
    with pytest.raises(ValueError, match='must be a directory'):
        _validate_report_path(str(file_path))
    with pytest.raises(ValueError, match='outside the repository'):
        _validate_external_directory(str(Path.cwd()), 'destination')
    assert _validate_optional_external_directory(None, 'destination') is None
    with pytest.raises(ValueError, match='no output directory'):
        _validate_case_output_roots(
            [
                ValidationCase(
                    case_id='cvm-bad',
                    source='cvm',
                    year=2024,
                    input_path='https://example.test/file.zip',
                    output_root='',
                    document='DFP',
                    mode='cvm',
                )
            ]
        )

    case = ValidationCase(
        case_id='case-a',
        source='cvm',
        year=2024,
        input_path='https://example.test/file.zip',
        output_root=str(tmp_path / 'output'),
        document='DFP',
        mode='cvm',
    )
    assert _filter_cases([case], 'case-a') == [case]
    with pytest.raises(ValueError, match='unknown validation case'):
        _filter_cases([case], 'case-b')


def test_cli_requires_source_and_positive_timeout() -> None:
    """Non-resume invocations require a source and positive timeout."""
    with pytest.raises(ValueError, match='source is required'):
        _required_source(None)
    with pytest.raises(ValueError, match='greater than zero'):
        _positive_timeout(0)
