"""Verify package execution without relying on script-directory imports."""

import runpy
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.process_runner import run_process
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration

EXAMPLE_MODULES = [
    'examples.01_quickstart_cvm',
    'examples.02_quickstart_b3',
    'examples.03_advanced_options_b3',
]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('module', [*EXAMPLE_MODULES, 'examples.04_yearly_b3'])
def test_module_entrypoint_reaches_option_validation(module):
    result = run_process(
        ['python', '-m', module, '--help'],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert result.returncode == 2
    assert 'Edit SETTINGS' in result.stderr
    assert 'Traceback' not in result.stderr
    assert result.stdout == ''


@pytest.mark.parametrize('module', EXAMPLE_MODULES[1:])
def test_b3_module_processes_local_quotes(
    module, tmp_path, monkeypatch, capsys
):
    directory = tmp_path / 'cotahist_b3'
    directory.mkdir()
    write_cotahist_txt(
        directory,
        year=2023,
        records=[
            build_cotahist_record(year=2023, ticker='PETR4', market='010')
        ],
    )
    namespace = runpy.run_module(module)
    settings = {
        'INITIAL_YEAR': 2023,
        'LAST_YEAR': 2023,
        'PATH_OF_DOCS': str(directory),
        'DESTINATION_PATH': str(tmp_path / 'output'),
        'OUTPUT_NAME': 'quotes',
    }
    for name, value in settings.items():
        monkeypatch.setitem(namespace['main'].__globals__, name, value)
    monkeypatch.setattr(sys, 'argv', [module])

    namespace['support'].run_example(namespace['main'])

    table = pq.read_table(tmp_path / 'output' / 'quotes_2023.parquet')
    assert table['ticker'].to_pylist() == ['PETR4']
    assert 'completed successfully' in capsys.readouterr().out
