"""End-to-end annual benchmark expectations and source identity regressions."""

from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts import benchmark_corpus, benchmark_runtime, benchmark_support
from scripts.benchmark_corpus.synthetic import write_b3_txt
from scripts.benchmark_runtime.operations import run_b3


@pytest.mark.integration
def test_annual_reference_preserves_cold_root_import_benchmark(
    tmp_path: Path,
) -> None:
    """The annual oracle must not preload engines in unrelated children."""
    source = benchmark_support.ScenarioInput('import_root', None, 0, '')
    records = benchmark_runtime.run_parent_scenario(
        source, repeats=1, root=tmp_path, git_sha='cold-root-regression'
    )

    assert records[0]['status'] == 'passed', records[0].get('reason')
    assert records[0]['logical_equivalence'] is True


@pytest.fixture
def annual_source(tmp_path: Path) -> benchmark_support.ScenarioInput:
    """Create all annual ZIPs, including block and unmapped market records."""
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    for year in range(2000, 2027):
        text = tmp_path / f'COTAHIST_A{year}.TXT'
        write_b3_txt(text, 2, year=year)
        lines = text.read_bytes().splitlines(keepends=True)
        lines[1] = lines[1][:24] + b'021' + lines[1][27:]
        lines[2] = lines[2][:24] + b'099' + lines[2][27:]
        payload = b''.join(lines)
        with zipfile.ZipFile(inputs / f'COTAHIST_A{year}.ZIP', 'w') as archive:
            archive.writestr(text.name, payload)
    return benchmark_corpus.prepare_input(
        'b3_annual', tmp_path, None, inputs, worker_limit=1
    )


@pytest.mark.integration
@pytest.mark.parametrize('mode', ['fast', 'slow'])
def test_annual_benchmark_matches_full_public_extraction(
    tmp_path: Path,
    annual_source: benchmark_support.ScenarioInput,
    mode: str,
) -> None:
    """Both public modes match independent expectations for all 32 fields."""
    source = replace(annual_source, processing_mode=mode)
    records = benchmark_runtime.run_parent_scenario(
        source, repeats=1, root=tmp_path, git_sha='annual-regression'
    )

    assert len(records) == 1
    assert records[0]['status'] == 'passed', records[0].get('reason')
    assert records[0]['row_count'] == 54
    assert records[0]['logical_digest'] == source.expected_digest
    assert records[0]['logical_equivalence'] is True


@pytest.mark.integration
@pytest.mark.parametrize('field', ['id_fonte', 'ano_origem'])
def test_annual_benchmark_rejects_changed_source_identity(
    tmp_path: Path,
    annual_source: benchmark_support.ScenarioInput,
    field: str,
) -> None:
    """Reject a changed source hash or year against the reference digest."""
    output_directory = tmp_path / 'output'
    run_b3(annual_source, output_directory, processing_mode='slow')
    output = output_directory / 'benchmark_quotes.parquet'
    table = pq.read_table(output)
    rows = table.to_pylist()
    rows[0][field] = '0' * 64 if field == 'id_fonte' else 1999
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), output)

    _, _, equivalent, _, observed_digest = (
        benchmark_runtime.validate_b3_output(output, annual_source)
    )

    assert equivalent is False
    assert observed_digest != annual_source.expected_digest
