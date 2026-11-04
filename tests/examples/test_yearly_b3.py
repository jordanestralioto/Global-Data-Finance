"""Verify annual B3 outputs and updates using local deterministic sources."""

import json
import runpy
import sys
from pathlib import Path
from shutil import copy2

import pyarrow.parquet as pq
import pytest

from scripts.process_runner import run_process
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE = 'examples.04_yearly_b3'


@pytest.fixture
def yearly_example(tmp_path, monkeypatch):
    """Run the real example with caller-owned sources and output paths."""
    directory = tmp_path / 'inputs'
    directory.mkdir()
    for year in (2022, 2023):
        write_cotahist_txt(
            directory,
            year=year,
            records=[build_cotahist_record(year=year, ticker=f'YEAR{year}')],
        )
    namespace = runpy.run_module(MODULE)
    main = namespace['main']
    settings = {
        'INITIAL_YEAR': 2022,
        'LAST_YEAR': 2023,
        'PATH_OF_DOCS': str(directory),
        'DESTINATION_PATH': str(tmp_path / 'annual output'),
    }
    for name, value in settings.items():
        monkeypatch.setitem(main.__globals__, name, value)
    monkeypatch.setattr(sys, 'argv', [MODULE])
    return namespace


def test_yearly_defaults_run_with_bundled_samples(tmp_path):
    """The default script persists one complete annual file per sample year."""
    inputs = tmp_path / 'cotahist_b3'
    inputs.mkdir()
    for year in (2022, 2023):
        name = f'COTAHIST_A{year}.ZIP'
        copy2(REPOSITORY_ROOT / 'cotahist_b3' / name, inputs / name)
    command = ['python', str(REPOSITORY_ROOT / 'examples/04_yearly_b3.py')]
    result = run_process(command, cwd=tmp_path, check=False)

    assert result.returncode == 0, result.stderr
    root = tmp_path / 'dados_b3/cotacoes_acoes_por_ano'
    assert sorted(path.name for path in root.iterdir()) == ['2022', '2023']
    for year in (2022, 2023):
        table = pq.read_table(
            root / str(year) / f'cotacoes_acoes_{year}.parquet'
        )
        assert table.num_rows == 12
        assert len(table.schema) == 32
        assert {day.year for day in table['data_pregao'].to_pylist()} == {year}
        assert set(table['tipo_mercado'].to_pylist()) == {'010', '020'}
        manifest = json.loads(
            table.schema.metadata[b'globaldatafinance.b3.integrity_manifest']
        )
        assert manifest['requested_years'] == [year]
        assert manifest['expected_counts']['written_rows'] == table.num_rows
        assert [source['year'] for source in manifest['sources']] == [year]


@pytest.mark.parametrize('mode', ['fast', 'slow'])
def test_updating_one_year_preserves_other_years(
    mode, yearly_example, tmp_path, monkeypatch
):
    """Refreshing one source replaces its file without duplicating rows."""
    main = yearly_example['main']
    monkeypatch.setitem(main.__globals__, 'PROCESSING_MODE', mode)
    main()
    root = tmp_path / 'annual output'
    previous = root / '2022/cotacoes_acoes_2022.parquet'
    previous_bytes = previous.read_bytes()
    previous_mtime = previous.stat().st_mtime_ns
    inputs = tmp_path / 'inputs'
    (inputs / 'COTAHIST_A2022.TXT').unlink()
    write_cotahist_txt(
        inputs,
        year=2023,
        records=[build_cotahist_record(year=2023, ticker='UPDATED')],
    )
    monkeypatch.setitem(main.__globals__, 'INITIAL_YEAR', 2023)

    main()

    assert previous.read_bytes() == previous_bytes
    assert previous.stat().st_mtime_ns == previous_mtime
    table = pq.read_table(root / '2023/cotacoes_acoes_2023.parquet')
    assert table['ticker'].to_pylist() == ['UPDATED']
    assert table['ano_origem'].to_pylist() == [2023]


def test_failed_year_stops_without_losing_completed_years(
    yearly_example, tmp_path, capsys
):
    """An unavailable year cannot turn a partial run into reported success."""
    (tmp_path / 'inputs/COTAHIST_A2023.TXT').unlink()
    with pytest.raises(SystemExit) as raised:
        yearly_example['support'].run_example(yearly_example['main'])

    assert raised.value.code == 1
    root = tmp_path / 'annual output'
    table = pq.read_table(root / '2022/cotacoes_acoes_2022.parquet')
    assert table['ticker'].to_pylist() == ['YEAR2022']
    assert not (root / '2023').exists()
    assert '2023' in capsys.readouterr().err


def test_reversed_year_range_fails_before_creating_output(
    yearly_example, tmp_path, monkeypatch
):
    """A reversed interval must fail before processing data."""
    main = yearly_example['main']
    monkeypatch.setitem(main.__globals__, 'INITIAL_YEAR', 2024)
    with pytest.raises(ValueError, match='LAST_YEAR'):
        main()

    assert not (tmp_path / 'annual output').exists()
