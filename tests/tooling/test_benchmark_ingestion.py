"""Contract tests for the reproducible ingestion benchmark runner."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import globaldatafinance
from globaldatafinance.brazil.b3_data import historical_quotes
from globaldatafinance.macro_exceptions import ExtractionError
from scripts import benchmark_corpus, benchmark_ingestion, benchmark_runtime


@pytest.mark.integration
def test_synthetic_cvm_benchmark_emits_a_fresh_child_median(
    tmp_path: Path,
) -> None:
    """A small deterministic CVM corpus produces a logically valid median."""
    source_path = tmp_path / 'cvm.zip'
    benchmark_ingestion._write_cvm_zip(source_path, 3)
    source = benchmark_ingestion.ScenarioInput(
        scenario='cvm',
        path=source_path,
        row_count=3,
        input_sha256=benchmark_ingestion._sha256_file(source_path),
        expected_first='0',
        expected_last='2',
    )

    records = benchmark_ingestion._run_parent_scenario(
        source, repeats=1, root=tmp_path, git_sha='test-sha'
    )
    medians = benchmark_ingestion._median_records(records)

    assert records[0]['status'] == 'passed'
    assert records[0]['logical_equivalence'] is True
    assert medians == [
        {
            'scenario': 'cvm',
            'successful_repeats': 1,
            'elapsed_seconds_median': records[0]['elapsed_seconds'],
            'rss_peak_mib_median': records[0]['rss_peak_mib'],
            'parent_rss_peak_mib_median': records[0]['parent_rss_peak_mib'],
            'aggregate_rss_peak_mib_median': records[0][
                'aggregate_rss_peak_mib'
            ],
            'output_bytes_median': records[0]['output_bytes'],
        }
    ]


@pytest.mark.integration
def test_synthetic_cvm_text_benchmark_emits_a_fresh_child_median(
    tmp_path: Path,
) -> None:
    """Wide-text CVM corpus runs safely end-to-end and validates."""
    source_path = tmp_path / 'cvm_text.zip'
    benchmark_ingestion._write_cvm_zip(source_path, 5, long_text=True)
    source = benchmark_ingestion.ScenarioInput(
        scenario='cvm_text',
        path=source_path,
        row_count=5,
        input_sha256=benchmark_ingestion._sha256_file(source_path),
        expected_first='0',
        expected_last='4',
    )

    records = benchmark_ingestion._run_parent_scenario(
        source, repeats=1, root=tmp_path, git_sha='test-sha'
    )
    medians = benchmark_ingestion._median_records(records)

    assert records[0]['status'] == 'passed'
    assert records[0]['logical_equivalence'] is True
    assert medians[0]['scenario'] == 'cvm_text'
    assert medians[0]['successful_repeats'] == 1


@pytest.mark.integration
def test_b3_benchmark_applies_source_and_worker_controls(
    tmp_path: Path,
) -> None:
    """A process request with one worker records the real thread fallback."""
    source = benchmark_corpus.prepare_input(
        'b3_multi_4x25k',
        tmp_path,
        100,
        None,
        backend='process',
        source_count=2,
        worker_limit=1,
    )

    records = benchmark_runtime.run_parent_scenario(
        source, repeats=1, root=tmp_path, git_sha='test-sha'
    )

    record = records[0]
    assert record['status'] == 'passed'
    assert record['requested_source_count'] == 2
    assert record['effective_source_count'] == 2
    assert record['requested_worker_limit'] == 1
    assert record['effective_worker_limit'] == 1
    assert record['effective_backend'] == 'thread'
    assert record['child_process_count_peak'] == 0


@pytest.mark.unit
def test_b3_runtime_scopes_executor_environment_and_restores_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Benchmark-only overrides neither need nor leak a facade argument."""
    observed: dict[str, str] = {}

    class FakeB3:
        """Minimal public-facade double that observes runtime configuration."""

        def __init__(self) -> None:
            """Capture the variables observed by facade construction."""
            observed['backend'] = os.environ['GDF_B3_EXECUTOR_BACKEND']
            observed['workers'] = os.environ['GDF_B3_WORKER_LIMIT']
            self._last_phase_timings: dict[str, Any] = {}

        def extract(self, **_kwargs: object) -> dict[str, object]:
            """Return the minimum successful facade result."""
            return {'success': True, 'output_file': str(tmp_path / 'quotes')}

    source = benchmark_corpus.ScenarioInput(
        'b3_multi_4x25k',
        tmp_path,
        2,
        '',
        executor_backend='process',
        source_count=2,
        worker_limit=2,
    )
    monkeypatch.setattr(globaldatafinance, 'HistoricalQuotesB3', FakeB3)
    monkeypatch.setattr(
        benchmark_runtime,
        'validate_b3_output',
        lambda _path, _source: (2, 'schema', True, 10, 'digest'),
    )
    monkeypatch.setattr(benchmark_runtime, '_last_b3_phase_timings', {})
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'thread')
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', '7')

    benchmark_runtime.run_b3(
        source,
        tmp_path / 'output',
        executor_backend='process',
    )

    assert observed == {'backend': 'process', 'workers': '2'}
    assert os.environ['GDF_B3_EXECUTOR_BACKEND'] == 'thread'
    assert os.environ['GDF_B3_WORKER_LIMIT'] == '7'


@pytest.mark.unit
def test_benchmark_cli_returns_non_zero_when_scenario_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A benchmark with a failed scenario returns a non-zero exit code."""
    monkeypatch.setattr(
        'sys.argv',
        [
            'benchmark_ingestion.py',
            '--scenario',
            'import_root',
            '--repeats',
            '1',
        ],
    )
    failed_record = {
        'scenario': 'import_root',
        'repeat_index': 0,
        'status': 'failed',
        'logical_equivalence': False,
        'elapsed_seconds': 0.1,
        'rss_peak_mib': 20.0,
        'output_bytes': 0,
    }
    monkeypatch.setattr(
        benchmark_ingestion,
        '_run_parent_scenario',
        lambda *_args, **_kwargs: [failed_record],
    )

    exit_code = benchmark_ingestion.main()
    assert exit_code == 1


@pytest.mark.unit
def test_non_equivalent_child_output_cannot_report_pass(
    tmp_path: Path,
) -> None:
    """Logical validation is a prerequisite for a passed benchmark result."""
    source = benchmark_ingestion.ScenarioInput('import_root', None, 0, '')
    result_path = tmp_path / 'result.json'

    def non_equivalent_op(
        _src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        return 1, 'schema', False, 1, 0.1, ''

    benchmark_ingestion._run_child(
        source, 0, result_path, operation=non_equivalent_op
    )
    payload = json.loads(result_path.read_text(encoding='utf-8'))

    assert payload['logical_equivalence'] is False
    assert payload['status'] == 'failed'
    assert payload['reason'] == (
        'output not logically equivalent to benchmark expectation'
    )


@pytest.mark.unit
def test_missing_annual_corpus_is_explicitly_skipped(tmp_path: Path) -> None:
    """External-data absence cannot be silently promoted to success."""
    source = benchmark_ingestion.ScenarioInput('b3_annual', None, 0, '')
    result_path = tmp_path / 'annual.json'

    benchmark_ingestion._run_child(source, 0, result_path)
    payload = json.loads(result_path.read_text(encoding='utf-8'))

    assert payload['status'] == 'skipped'
    assert payload['reason'] == 'external corpus unavailable'


@pytest.mark.unit
def test_incomplete_annual_corpus_is_explicitly_skipped(
    tmp_path: Path,
) -> None:
    """A partial local COTAHIST directory is not an annual benchmark corpus."""
    for year in (2022, 2023):
        (tmp_path / f'COTAHIST_A{year}.ZIP').touch()

    source = benchmark_corpus.prepare_input(
        'b3_annual', tmp_path, None, tmp_path
    )

    assert source.path is None
    assert source.input_sha256 == ''


@pytest.mark.unit
def test_changed_benchmark_input_cannot_report_pass(tmp_path: Path) -> None:
    """The child rejects an input modified after its checksum was recorded."""
    source_path = tmp_path / 'cvm.zip'
    benchmark_corpus.write_cvm_zip(source_path, 1)
    source = benchmark_corpus.ScenarioInput(
        'cvm',
        source_path,
        1,
        benchmark_corpus.sha256_file(source_path),
    )
    source_path.write_bytes(b'changed')
    result_path = tmp_path / 'result.json'

    benchmark_runtime.run_child(source, 0, result_path)
    payload = json.loads(result_path.read_text(encoding='utf-8'))

    assert payload['status'] == 'failed'
    assert payload['reason'].startswith('ValueError: Benchmark input checksum')


@pytest.mark.integration
def test_b3_middle_row_mutation_fails_logical_validation(
    tmp_path: Path,
) -> None:
    """A changed value away from the boundaries cannot pass validation."""
    rows = [benchmark_corpus._expected_b3_record(index) for index in range(3)]
    rows[1]['preco_abertura'] = Decimal('9999.99')
    output = tmp_path / 'quotes.parquet'
    pq.write_table(
        pa.Table.from_pylist(
            rows, schema=historical_quotes.parquet_writer.build_b3_schema()
        ),
        output,
    )
    source = benchmark_ingestion.ScenarioInput(
        scenario='b3_100k',
        path=None,
        row_count=3,
        input_sha256='',
        expected_first='GD0000000000',
        expected_last='GD0000000002',
        expected_digest=benchmark_corpus.expected_b3_digest(3),
    )

    _, _, equivalent, _, _ = benchmark_runtime.validate_b3_output(
        output, source
    )

    assert equivalent is False


@pytest.mark.integration
def test_annual_b3_output_without_trusted_digest_cannot_report_equivalence(
    tmp_path: Path,
) -> None:
    """Annual output needs a full digest before it can pass validation."""
    rows = [benchmark_corpus._expected_b3_record(index) for index in range(3)]
    rows[1]['preco_abertura'] = Decimal('9999.99')
    output = tmp_path / 'annual_quotes.parquet'
    pq.write_table(
        pa.Table.from_pylist(
            rows, schema=historical_quotes.parquet_writer.build_b3_schema()
        ),
        output,
    )
    source = benchmark_corpus.ScenarioInput(
        scenario='b3_annual',
        path=None,
        row_count=0,
        input_sha256='',
    )

    _, _, equivalent, _, digest = benchmark_runtime.validate_b3_output(
        output, source
    )

    assert digest
    assert equivalent is False


@pytest.mark.integration
def test_annual_corpus_builds_a_full_typed_digest_and_actual_source_count(
    tmp_path: Path,
) -> None:
    """The annual manifest covers all rows, not only ticker boundaries."""
    for index, year in enumerate(benchmark_corpus._ANNUAL_B3_YEARS):
        source = tmp_path / f'COTAHIST_A{year}.ZIP'
        payload = (
            '00COTAHIST BENCHMARK\n'
            f'{benchmark_corpus.b3_record(index)}\n'
            '99COTAHIST BENCHMARK\n'
        )
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr(f'COTAHIST_A{year}.TXT', payload)

    prepared = benchmark_corpus.prepare_input(
        'b3_annual', tmp_path, None, tmp_path
    )

    assert prepared.source_count == len(benchmark_corpus._ANNUAL_B3_YEARS)
    assert prepared.expected_digest == benchmark_corpus.expected_b3_digest(
        len(benchmark_corpus._ANNUAL_B3_YEARS)
    )


@pytest.mark.unit
def test_run_child_accepts_injected_operation(tmp_path: Path) -> None:
    """An explicitly injected child operation is called without globals."""
    source = benchmark_corpus.ScenarioInput('import_root', None, 0, '')
    result_path = tmp_path / 'injected.json'
    called: list[str] = []

    def custom_op(
        src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        called.append(src.scenario)
        return 0, 'custom_fp', True, 0, 0.05, 'custom_digest'

    benchmark_runtime.run_child(source, 0, result_path, operation=custom_op)
    payload = json.loads(result_path.read_text(encoding='utf-8'))

    assert called == ['import_root']
    assert payload['status'] == 'passed'
    assert payload['logical_equivalence'] is True
    assert payload['schema_fingerprint'] == 'custom_fp'


@pytest.mark.unit
@pytest.mark.parametrize(
    ('exception_cls', 'message'),
    [
        (ExtractionError, 'cvm extraction failure'),
        (ValueError, 'invalid data parameter'),
        (RuntimeError, 'process execution died'),
        (OSError, 'disk write I/O error'),
    ],
)
def test_run_child_normalizes_operational_exceptions(
    tmp_path: Path,
    exception_cls: type[Exception],
    message: str,
) -> None:
    """Operational failures are normalized to failed status with reason."""
    source = benchmark_corpus.ScenarioInput('cvm', None, 0, '')
    result_path = tmp_path / 'operational_error.json'

    def failing_op(
        _src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        if exception_cls is ExtractionError:
            raise ExtractionError('/fake/path.zip', message)
        raise exception_cls(message)

    benchmark_runtime.run_child(source, 0, result_path, operation=failing_op)
    payload = json.loads(result_path.read_text(encoding='utf-8'))

    assert payload['status'] == 'failed'
    assert payload['logical_equivalence'] is False
    assert message in payload['reason']
    assert payload['reason'].startswith(f'{exception_cls.__name__}:')


@pytest.mark.unit
def test_run_child_propagates_unexpected_exceptions(tmp_path: Path) -> None:
    """Unexpected programming bugs propagate uncaught instead of failing."""
    source = benchmark_corpus.ScenarioInput('cvm', None, 0, '')
    result_path = tmp_path / 'unexpected_error.json'

    def bug_op(
        _src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        raise KeyError('unhandled_programming_bug')

    with pytest.raises(KeyError, match='unhandled_programming_bug'):
        benchmark_runtime.run_child(source, 0, result_path, operation=bug_op)


@pytest.mark.unit
def test_median_records_aggregates_multiple_scenarios_in_single_pass() -> None:
    """Median records aggregates multiple scenarios with mixed statuses."""
    records = [
        {
            'scenario': 'scenario_a',
            'status': 'passed',
            'elapsed_seconds': 1.0,
            'rss_peak_mib': 10.0,
            'output_bytes': 100,
        },
        {
            'scenario': 'scenario_a',
            'status': 'passed',
            'elapsed_seconds': 3.0,
            'rss_peak_mib': 30.0,
            'output_bytes': 300,
        },
        {
            'scenario': 'scenario_a',
            'status': 'passed',
            'elapsed_seconds': 2.0,
            'rss_peak_mib': 20.0,
            'output_bytes': 200,
        },
        {
            'scenario': 'scenario_b',
            'status': 'passed',
            'elapsed_seconds': 5.0,
            'rss_peak_mib': 50.0,
            'output_bytes': 500,
        },
        {
            'scenario': 'scenario_b',
            'status': 'failed',
            'elapsed_seconds': 0.1,
            'rss_peak_mib': 5.0,
            'output_bytes': 0,
        },
        {
            'scenario': 'scenario_c',
            'status': 'skipped',
            'elapsed_seconds': 0.0,
            'rss_peak_mib': 0.0,
            'output_bytes': 0,
        },
    ]
    medians = benchmark_runtime.median_records(records)
    assert medians == [
        {
            'scenario': 'scenario_a',
            'successful_repeats': 3,
            'elapsed_seconds_median': 2.0,
            'rss_peak_mib_median': 20.0,
            'parent_rss_peak_mib_median': 20.0,
            'aggregate_rss_peak_mib_median': 20.0,
            'output_bytes_median': 200,
        },
        {
            'scenario': 'scenario_b',
            'successful_repeats': 1,
            'elapsed_seconds_median': 5.0,
            'rss_peak_mib_median': 50.0,
            'parent_rss_peak_mib_median': 50.0,
            'aggregate_rss_peak_mib_median': 50.0,
            'output_bytes_median': 500,
        },
    ]


@pytest.mark.unit
def test_benchmark_record_exact_keys_for_passed_failed_and_skipped(
    tmp_path: Path,
) -> None:
    """Benchmark output JSON files contain the exact expected schema keys."""
    expected_passed_keys = {
        'aggregate_rss_peak_mib',
        'artifact_sha256',
        'available_memory_mib',
        'child_process_count_peak',
        'cpu_count',
        'effective_backend',
        'effective_source_count',
        'effective_worker_limit',
        'elapsed_seconds',
        'executor_backend',
        'git_sha',
        'input_sha256',
        'logical_digest',
        'logical_equivalence',
        'output_bytes',
        'parent_rss_after_mib',
        'parent_rss_before_mib',
        'parent_rss_peak_mib',
        'phase_seconds',
        'platform',
        'processing_mode',
        'python_version',
        'repeat_index',
        'requested_backend',
        'requested_source_count',
        'requested_worker_limit',
        'row_count',
        'rss_after_mib',
        'rss_before_mib',
        'rss_peak_mib',
        'scenario',
        'schema_fingerprint',
        'schema_version',
        'source_count',
        'status',
        'timestamp',
        'worker_limit',
        'worker_pids_observed',
        'worktree_sha256',
    }
    expected_unmeasured_keys = expected_passed_keys | {'reason'}

    source_pass = benchmark_corpus.ScenarioInput('import_root', None, 0, '')
    pass_file = tmp_path / 'pass.json'

    def pass_op(
        _src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        return 0, 'dummy_fp', True, 10, 0.01, 'dummy_digest'

    benchmark_runtime.run_child(source_pass, 0, pass_file, operation=pass_op)
    pass_payload = json.loads(pass_file.read_text(encoding='utf-8'))
    assert set(pass_payload.keys()) == expected_passed_keys
    assert pass_payload['status'] == 'passed'

    fail_file = tmp_path / 'fail.json'

    def fail_op(
        _src: benchmark_corpus.ScenarioInput, _out: Path
    ) -> benchmark_runtime.OperationResult:
        raise ValueError('operational boom')

    benchmark_runtime.run_child(source_pass, 0, fail_file, operation=fail_op)
    fail_payload = json.loads(fail_file.read_text(encoding='utf-8'))
    assert set(fail_payload.keys()) == expected_unmeasured_keys
    assert fail_payload['status'] == 'failed'

    source_skip = benchmark_corpus.ScenarioInput('b3_annual', None, 0, '')
    skip_file = tmp_path / 'skip.json'
    benchmark_runtime.run_child(source_skip, 0, skip_file)
    skip_payload = json.loads(skip_file.read_text(encoding='utf-8'))
    assert set(skip_payload.keys()) == expected_unmeasured_keys
    assert skip_payload['status'] == 'skipped'


@pytest.mark.unit
def test_benchmark_cli_returns_zero_when_scenarios_pass_or_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A benchmark with only passed and skipped scenarios exits with zero."""
    monkeypatch.setattr(
        'sys.argv',
        [
            'benchmark_ingestion.py',
            '--scenario',
            'import_root',
            '--repeats',
            '1',
        ],
    )
    records = [
        {
            'scenario': 'import_root',
            'repeat_index': 0,
            'status': 'passed',
            'logical_equivalence': True,
            'elapsed_seconds': 0.1,
            'rss_peak_mib': 20.0,
            'output_bytes': 0,
        },
        {
            'scenario': 'b3_annual',
            'repeat_index': 0,
            'status': 'skipped',
            'reason': 'external corpus unavailable',
            'logical_equivalence': False,
            'elapsed_seconds': 0.0,
            'rss_peak_mib': 0.0,
            'output_bytes': 0,
        },
    ]
    monkeypatch.setattr(
        benchmark_ingestion,
        '_run_parent_scenario',
        lambda *_args, **_kwargs: records,
    )

    exit_code = benchmark_ingestion.main()
    assert exit_code == 0


@pytest.mark.unit
def test_b3_multi_corpus_remainder_distribution(tmp_path: Path) -> None:
    """Rows remainder is cleanly distributed across the requested files."""
    source = benchmark_corpus.prepare_input(
        'b3_multi_4x25k',
        tmp_path,
        10,
        None,
        source_count=3,
        worker_limit=2,
    )
    assert source.row_count == 10
    assert source.source_count == 3
    assert source.worker_limit == 2
    files = sorted(tmp_path.glob('b3_multi_4x25k/COTAHIST_A*.TXT'))
    assert len(files) == 3
    # Header (1) + data + trailer (1)
    line_counts = [
        len(f.read_text(encoding='latin1').splitlines()) - 2 for f in files
    ]
    assert line_counts == [4, 3, 3]
    assert sum(line_counts) == 10


@pytest.mark.unit
@pytest.mark.parametrize(
    ('source_count', 'worker_limit'),
    [(0, 1), (-1, 1), (1, 0), (1, -2)],
)
def test_b3_multi_corpus_invalid_counts_raise(
    tmp_path: Path, source_count: int, worker_limit: int
) -> None:
    """Non-positive source count or worker limit raises ValueError."""
    with pytest.raises(ValueError, match='must be at least 1'):
        benchmark_corpus.prepare_input(
            'b3_multi_4x25k',
            tmp_path,
            10,
            None,
            source_count=source_count,
            worker_limit=worker_limit,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ('arg_flag', 'val'),
    [('--source-count', '0'), ('--worker-limit', '0')],
)
def test_benchmark_cli_validates_positive_counts(
    monkeypatch: pytest.MonkeyPatch, arg_flag: str, val: str
) -> None:
    """CLI rejects non-positive source-count and worker-limit."""
    monkeypatch.setattr(
        'sys.argv',
        ['benchmark_ingestion.py', '--scenario', 'import_root', arg_flag, val],
    )
    with pytest.raises(SystemExit, match='must be at least one'):
        benchmark_ingestion.main()


@pytest.mark.unit
def test_b3_multi_corpus_source_count_greater_than_rows_raises(
    tmp_path: Path,
) -> None:
    """prepare_input rejects source_count greater than rows."""
    with pytest.raises(ValueError, match='cannot be greater than rows'):
        benchmark_corpus.prepare_input(
            'b3_multi_4x25k',
            tmp_path,
            2,
            None,
            source_count=5,
        )


@pytest.mark.unit
def test_b3_multi_corpus_source_count_exceeds_max_years_raises(
    tmp_path: Path,
) -> None:
    """prepare_input rejects source_count exceeding available years."""
    with pytest.raises(ValueError, match='exceeds maximum allowed years'):
        benchmark_corpus.prepare_input(
            'b3_multi_4x25k',
            tmp_path,
            100,
            None,
            source_count=99,
        )


@pytest.mark.unit
def test_benchmark_cli_validates_source_count_not_greater_than_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI rejects --source-count greater than --rows."""
    monkeypatch.setattr(
        'sys.argv',
        [
            'benchmark_ingestion.py',
            '--scenario',
            'b3_multi_4x25k',
            '--rows',
            '2',
            '--source-count',
            '5',
        ],
    )
    with pytest.raises(SystemExit, match='cannot be greater than --rows'):
        benchmark_ingestion.main()


@pytest.mark.unit
def test_benchmark_cli_converts_dynamic_source_count_limit_to_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The synthetic-year bound is a CLI error, never an uncaught traceback."""
    source_count = datetime.now(UTC).year - 2020 + 1
    monkeypatch.setattr(
        'sys.argv',
        [
            'benchmark_ingestion.py',
            '--scenario',
            'b3_multi_4x25k',
            '--rows',
            str(source_count),
            '--source-count',
            str(source_count),
        ],
    )

    with pytest.raises(SystemExit, match='exceeds maximum allowed years'):
        benchmark_ingestion.main()


@pytest.mark.unit
def test_annual_corpus_rejects_source_count_override(tmp_path: Path) -> None:
    """Annual runs must expose the fixed source count they actually process."""
    with pytest.raises(ValueError, match='not supported for b3_annual'):
        benchmark_corpus.prepare_input(
            'b3_annual', tmp_path, None, tmp_path, source_count=99
        )


@pytest.mark.unit
def test_benchmark_cli_rejects_annual_source_count_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command-line form rejects an annual override before measurement."""
    monkeypatch.setattr(
        'sys.argv',
        [
            'benchmark_ingestion.py',
            '--scenario',
            'b3_annual',
            '--source-count',
            '27',
        ],
    )

    with pytest.raises(SystemExit, match='only supported by b3_multi_4x25k'):
        benchmark_ingestion.main()


@pytest.mark.unit
def test_dirty_git_provenance_includes_diff_and_untracked_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dirty benchmark record identifies the exact uncommitted content."""
    untracked = tmp_path / 'new_module.py'
    untracked.write_text('value = 1\n', encoding='utf-8')
    status = ' M tracked.py\n?? new_module.py\n'
    diff = 'diff --git a/tracked.py b/tracked.py\n'

    def fake_run_process(
        command: list[str], **_kwargs: object
    ) -> SimpleNamespace:
        if command[1:3] == ['rev-parse', 'HEAD']:
            return SimpleNamespace(stdout='abc123\n')
        if command[1:3] == ['status', '--porcelain']:
            return SimpleNamespace(stdout=status)
        if command[1:3] == ['diff', '--no-ext-diff']:
            return SimpleNamespace(stdout=diff)
        if command[1:3] == ['ls-files', '--others']:
            return SimpleNamespace(stdout='new_module.py\n')
        raise AssertionError(command)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(benchmark_ingestion, 'run_process', fake_run_process)
    monkeypatch.setattr(
        benchmark_ingestion, '_sha256_file', lambda _path: 'content-digest'
    )

    git_sha, worktree_sha256 = benchmark_ingestion._current_git_provenance()

    expected = hashlib.sha256()
    expected.update(status.encode('utf-8'))
    expected.update(diff.encode('utf-8'))
    expected.update(b'new_module.py')
    expected.update(b'content-digest')
    assert git_sha == 'abc123-dirty'
    assert worktree_sha256 == expected.hexdigest()
