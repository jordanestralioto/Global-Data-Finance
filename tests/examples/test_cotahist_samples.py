"""Protect clone-ready B3 examples and their reproducible synthetic inputs."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copy2

import pyarrow.parquet as pq
import pytest

from scripts import generate_example_cotahist
from scripts.process_runner import run_process

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ('script', 'output', 'years', 'markets', 'expected_rows'),
    [
        (
            '02_quickstart_b3.py',
            'cotacoes_acoes_2023.parquet',
            {2023},
            {'010', '020'},
            3,
        ),
        (
            '03_advanced_options_b3.py',
            'carteira_completa_2022_2023.parquet',
            {2022, 2023},
            {'010', '020', '070', '080'},
            10,
        ),
    ],
)
def test_default_b3_examples_run_with_only_bundled_inputs(
    script, output, years, markets, expected_rows, tmp_path
):
    """A fresh working directory needs no local dataset or setting edits."""
    inputs = tmp_path / 'cotahist_b3'
    inputs.mkdir()
    for year in (2022, 2023):
        name = f'COTAHIST_A{year}.ZIP'
        copy2(REPOSITORY_ROOT / 'cotahist_b3' / name, inputs / name)

    result = run_process(
        ['python', str(REPOSITORY_ROOT / 'examples' / script)],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert 'completed successfully' in result.stdout
    table = pq.read_table(tmp_path / 'dados_b3' / output)
    assert table.num_rows == expected_rows
    assert set(table['tipo_mercado'].to_pylist()) == markets
    assert set(table['data_pregao'].to_pylist()) == {
        date(year, 1, 15) for year in years
    }
    assert set(table['preco_fechamento'].to_pylist()) == {Decimal('123.45')}
    assert len(table.schema) == 32
    assert (
        table.schema.metadata[b'globaldatafinance.b3.schema_version'] == b'2'
    )


def test_bundled_inputs_match_the_canonical_generator():
    """Changes to the synthetic source require regenerating committed ZIPs."""
    assert (
        generate_example_cotahist.check_samples(
            REPOSITORY_ROOT / 'cotahist_b3'
        )
        == ()
    )


def test_check_reports_changed_and_missing_inputs_without_rewriting(
    tmp_path, monkeypatch, capsys
):
    """Verification detects both drift and missing artifacts without repair."""
    generate_example_cotahist.write_samples(tmp_path)
    changed = tmp_path / 'COTAHIST_A2022.ZIP'
    missing = tmp_path / 'COTAHIST_A2023.ZIP'
    changed.write_bytes(b'changed sample')
    missing.unlink()
    monkeypatch.setattr(
        generate_example_cotahist, 'SAMPLES_DIRECTORY', tmp_path
    )

    status = generate_example_cotahist.main(['--check'])

    assert status == 1
    assert changed.read_bytes() == b'changed sample'
    assert not missing.exists()
    message = capsys.readouterr().err
    assert 'COTAHIST_A2022.ZIP' in message
    assert 'COTAHIST_A2023.ZIP' in message
