"""Contract tests for the reproducible ingestion benchmark runner."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

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
            'output_bytes_median': 200,
        },
        {
            'scenario': 'scenario_b',
            'successful_repeats': 1,
            'elapsed_seconds_median': 5.0,
            'rss_peak_mib_median': 50.0,
            'output_bytes_median': 500,
        },
    ]


@pytest.mark.unit
def test_benchmark_record_exact_keys_for_passed_failed_and_skipped(
    tmp_path: Path,
) -> None:
    """Benchmark output JSON files contain the exact expected schema keys."""
    expected_passed_keys = {
        'available_memory_mib',
        'cpu_count',
        'elapsed_seconds',
        'git_sha',
        'input_sha256',
        'logical_digest',
        'logical_equivalence',
        'output_bytes',
        'phase_seconds',
        'platform',
        'python_version',
        'repeat_index',
        'row_count',
        'rss_after_mib',
        'rss_before_mib',
        'rss_peak_mib',
        'scenario',
        'schema_fingerprint',
        'schema_version',
        'status',
        'timestamp',
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
