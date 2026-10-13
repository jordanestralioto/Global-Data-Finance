"""Execute every example and check the persisted data and failure behavior."""

from __future__ import annotations

import re
import runpy
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.process_runner import run_process
from tests.support.builders import (
    build_cotahist_record,
    csv_bytes,
    write_cotahist_txt,
    write_cotahist_zip,
    write_zip,
)
from tests.support.fake_http import FakeResponse, install_fake_http_client

pytestmark = pytest.mark.integration

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / 'examples'
CVM_SCRIPT = '01_quickstart_cvm.py'
B3_EXAMPLES = [
    ('02_quickstart_b3.py', 'cotacoes_acoes', {'010', '020'}),
    (
        '03_advanced_options_b3.py',
        'carteira_completa',
        {'010', '020', '070', '080'},
    ),
]
QUOTES = [
    ('PETR4', '010'),
    ('BOVA11', '010'),
    ('PETR4F', '020'),
    ('PETRA1', '070'),
    ('PETRM1', '080'),
    ('PETR4T', '030'),
]


def _configured_example(monkeypatch, script, **settings):
    """Load a script and edit its settings without touching personal paths."""
    monkeypatch.syspath_prepend(str(EXAMPLES_DIR))
    namespace = runpy.run_path(str(EXAMPLES_DIR / script))
    for name, value in settings.items():
        monkeypatch.setitem(namespace['main'].__globals__, name, value)
    monkeypatch.setattr(sys, 'argv', [script])
    return namespace


@pytest.fixture(params=['ZIP', 'TXT'])
def cotahist_directory(tmp_path, request):
    directory = tmp_path / 'cotahist_b3'
    directory.mkdir()
    writer = (
        write_cotahist_zip if request.param == 'ZIP' else write_cotahist_txt
    )
    for year in (2022, 2023):
        writer(
            directory,
            year=year,
            records=[
                build_cotahist_record(year=year, ticker=ticker, market=market)
                for ticker, market in QUOTES
            ],
        )
    return directory


@pytest.mark.parametrize(
    'script', [CVM_SCRIPT, *[example[0] for example in B3_EXAMPLES]]
)
@pytest.mark.parametrize('options', [['--help'], ['--initial-year', '2023']])
def test_every_script_rejects_terminal_options_without_creating_files(
    script, options, tmp_path
):
    result = run_process(
        ['python', str(EXAMPLES_DIR / script), *options],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ''
    assert 'Edit SETTINGS' in result.stderr
    assert 'Traceback' not in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(('script', 'basename', 'markets'), B3_EXAMPLES)
def test_b3_defaults_write_only_the_selected_2023_quotes(
    script,
    basename,
    markets,
    cotahist_directory,
    tmp_path,
    monkeypatch,
    capsys,
):
    original_files = {
        path.name: path.read_bytes() for path in cotahist_directory.iterdir()
    }
    namespace = _configured_example(
        monkeypatch,
        script,
        INITIAL_YEAR=2023,
        LAST_YEAR=2023,
        PATH_OF_DOCS=str(cotahist_directory),
    )
    monkeypatch.chdir(tmp_path)
    namespace['support'].run_example(namespace['main'])
    messages = capsys.readouterr().out
    output = tmp_path / 'dados_b3' / f'{basename}_2023.parquet'
    table = pq.read_table(output)
    expected_tickers = {
        ticker for ticker, market in QUOTES if market in markets
    }

    assert output.is_file()
    assert 'completed successfully' in messages
    assert str(output) in messages
    assert ('Processing mode: fast' in messages) == (
        script == '03_advanced_options_b3.py'
    )
    assert table.num_rows == len(expected_tickers)
    assert set(table['ticker'].to_pylist()) == expected_tickers
    assert set(table['tipo_mercado'].to_pylist()) == markets
    assert set(table['data_pregao'].to_pylist()) == {date(2023, 1, 15)}
    assert set(table['preco_fechamento'].to_pylist()) == {Decimal('123.45')}
    assert (
        table.schema.metadata[b'globaldatafinance.b3.schema_version'] == b'2'
    )
    assert {
        path.name: path.read_bytes() for path in cotahist_directory.iterdir()
    } == original_files


@pytest.mark.parametrize(('script', '_basename', '_markets'), B3_EXAMPLES)
@pytest.mark.parametrize(
    ('assets', 'markets'),
    [
        (['todos'], {'010', '020', '030', '070', '080'}),
        (['opções'], {'070', '080'}),
    ],
)
def test_b3_edited_settings_control_the_persisted_output(
    script,
    _basename,
    _markets,
    assets,
    markets,
    cotahist_directory,
    tmp_path,
    monkeypatch,
    capsys,
):
    output_dir = tmp_path / 'edited output with spaces'
    namespace = _configured_example(
        monkeypatch,
        script,
        INITIAL_YEAR=2022,
        LAST_YEAR=2023,
        PATH_OF_DOCS=str(cotahist_directory),
        DESTINATION_PATH=str(output_dir),
        ASSETS=assets,
        OUTPUT_NAME='my_quotes',
        PROCESSING_MODE='slow',
        VERBOSE=False,
    )

    namespace['support'].run_example(namespace['main'])
    table = pq.read_table(output_dir / 'my_quotes_2022_2023.parquet')

    assert set(table['tipo_mercado'].to_pylist()) == markets
    assert set(table['data_pregao'].to_pylist()) == {
        date(2022, 1, 15),
        date(2023, 1, 15),
    }
    assert table.num_rows == 2 * sum(market in markets for _, market in QUOTES)
    assert 'Total processed files: 2' in capsys.readouterr().out


@pytest.mark.parametrize(('script', 'basename', 'markets'), B3_EXAMPLES)
@pytest.mark.parametrize('mode', ['fast', 'slow'])
def test_b3_custom_paths_range_and_modes_preserve_selected_quotes(
    script,
    basename,
    markets,
    mode,
    cotahist_directory,
    tmp_path,
    monkeypatch,
    capsys,
):
    output_dir = tmp_path / 'output with spaces'
    namespace = _configured_example(
        monkeypatch,
        script,
        PATH_OF_DOCS=str(cotahist_directory),
        INITIAL_YEAR=2022,
        LAST_YEAR=2023,
        PROCESSING_MODE=mode,
        DESTINATION_PATH=str(output_dir),
    )
    namespace['support'].run_example(namespace['main'])
    table = pq.read_table(output_dir / f'{basename}_2022_2023.parquet')

    assert (output_dir / f'{basename}_2022_2023.parquet').is_file()
    assert set(table['tipo_mercado'].to_pylist()) == markets
    assert set(table['data_pregao'].to_pylist()) == {
        date(2022, 1, 15),
        date(2023, 1, 15),
    }
    assert table.num_rows == 2 * sum(market in markets for _, market in QUOTES)
    assert 'Total processed files: 2' in capsys.readouterr().out


@pytest.mark.parametrize(('script', 'basename', 'markets'), B3_EXAMPLES)
def test_b3_matching_year_settings_select_one_year_in_the_output(
    script,
    basename,
    markets,
    cotahist_directory,
    tmp_path,
    monkeypatch,
    capsys,
):
    namespace = _configured_example(
        monkeypatch,
        script,
        INITIAL_YEAR=2022,
        LAST_YEAR=2022,
        PATH_OF_DOCS=str(cotahist_directory),
    )
    monkeypatch.chdir(tmp_path)
    namespace['support'].run_example(namespace['main'])
    table = pq.read_table(tmp_path / 'dados_b3' / f'{basename}_2022.parquet')

    assert (tmp_path / 'dados_b3' / f'{basename}_2022.parquet').is_file()
    assert set(table['data_pregao'].to_pylist()) == {date(2022, 1, 15)}
    assert set(table['tipo_mercado'].to_pylist()) == markets
    assert 'Total processed files: 1' in capsys.readouterr().out


@pytest.mark.parametrize(('script', '_basename', '_markets'), B3_EXAMPLES)
@pytest.mark.parametrize(
    'failure',
    [
        'missing_directory',
        'missing_year',
        'corrupt_input',
        'no_selected_records',
    ],
)
def test_b3_failures_exit_nonzero_and_never_report_success(
    script, _basename, _markets, failure, tmp_path, monkeypatch, capsys
):
    directory = tmp_path / 'cotahist_b3'
    if failure != 'missing_directory':
        directory.mkdir()
        if failure == 'corrupt_input':
            (directory / 'COTAHIST_A2023.ZIP').write_bytes(b'Invalid ZIP')
        else:
            write_cotahist_txt(
                directory,
                year=2022 if failure == 'missing_year' else 2023,
                records=[
                    build_cotahist_record(
                        year=2022 if failure == 'missing_year' else 2023,
                        market='030',
                    )
                ],
            )
    namespace = _configured_example(
        monkeypatch,
        script,
        PATH_OF_DOCS=str(directory),
        INITIAL_YEAR=2023,
        LAST_YEAR=2023,
        DESTINATION_PATH=str(tmp_path / 'output'),
    )
    with pytest.raises(SystemExit) as error:
        namespace['support'].run_example(namespace['main'])
    messages = capsys.readouterr()

    assert error.value.code == 1
    assert messages.err.strip()
    assert 'completed successfully' not in messages.out
    assert 'Traceback' not in messages.err


def _run_cvm_script(monkeypatch, **settings):
    configured = {
        'INITIAL_YEAR': 2023,
        'LAST_YEAR': 2023,
        'DOCUMENTS': ['DFP'],
    }
    configured.update(settings)
    namespace = _configured_example(
        monkeypatch,
        CVM_SCRIPT,
        **configured,
    )
    namespace['support'].run_example(namespace['main'])


@pytest.mark.parametrize('year', [2023, 2022])
def test_cvm_downloads_the_selected_year_and_converts_actual_zip_csv(
    year, tmp_path, monkeypatch, capsys
):
    payload = write_zip(
        tmp_path / 'response.zip',
        {
            'dfp.csv': csv_bytes(
                ['id;name', '1;João', '2;Ação'], encoding='latin-1'
            )
        },
    ).read_bytes()
    urls = []

    def response_factory(url):
        urls.append(url)
        return FakeResponse(
            url, [payload], headers={'content-length': str(len(payload))}
        )

    install_fake_http_client(monkeypatch, response_factory)
    monkeypatch.chdir(tmp_path)
    _run_cvm_script(monkeypatch, INITIAL_YEAR=year, LAST_YEAR=year)
    output_dir = tmp_path / 'dados_cvm'
    files = list(output_dir.rglob('*.parquet'))

    assert urls
    assert set(urls) == {
        f'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
        f'dfp_cia_aberta_{year}.zip'
    }
    assert len(files) == 1
    assert pq.read_table(files[0]).to_pylist() == [
        {'id': '1', 'name': 'João'},
        {'id': '2', 'name': 'Ação'},
    ]
    assert pq.read_table(files[0]).schema.metadata[b'cvm.contract'] == (
        b'exact-text-v1'
    )
    retained_archives = list(output_dir.rglob('*.zip'))
    assert len(retained_archives) == 1
    assert retained_archives[0].read_bytes() == payload
    assert 'completed successfully' in capsys.readouterr().out


def test_cvm_custom_destination_and_multiyear_download(
    tmp_path, monkeypatch, capsys
):
    payload = write_zip(
        tmp_path / 'response.zip', {'dfp.csv': 'id;value\n1;10\n'}
    ).read_bytes()
    urls = []

    def response_factory(url):
        urls.append(url)
        return FakeResponse(
            url, [payload], headers={'content-length': str(len(payload))}
        )

    install_fake_http_client(monkeypatch, response_factory)
    output_dir = tmp_path / 'CVM output with spaces'
    _run_cvm_script(
        monkeypatch,
        INITIAL_YEAR=2022,
        LAST_YEAR=2023,
        DESTINATION_PATH=str(output_dir),
    )

    assert {url.rsplit('_', 1)[-1] for url in urls} == {'2022.zip', '2023.zip'}
    assert len(list(output_dir.rglob('*.parquet'))) == 2
    assert 'Downloaded files count: 2' in capsys.readouterr().out


@pytest.mark.parametrize('automatic_extractor', [True, False])
def test_cvm_edited_settings_select_document_types_years_and_conversion(
    automatic_extractor, tmp_path, monkeypatch, capsys
):
    payload = write_zip(
        tmp_path / 'response.zip', {'statements.csv': 'id;value\n1;10\n'}
    ).read_bytes()
    urls = []

    def response_factory(url):
        urls.append(url)
        return FakeResponse(
            url, [payload], headers={'content-length': str(len(payload))}
        )

    install_fake_http_client(monkeypatch, response_factory)
    output_dir = tmp_path / 'edited CVM output'
    namespace = _configured_example(
        monkeypatch,
        CVM_SCRIPT,
        INITIAL_YEAR=2022,
        LAST_YEAR=2023,
        DESTINATION_PATH=str(output_dir),
        DOCUMENTS=['DFP', 'ITR'],
        AUTOMATIC_EXTRACTOR=automatic_extractor,
    )
    namespace['support'].run_example(namespace['main'])

    assert set(urls) == {
        f'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{document}/DADOS/'
        f'{document.lower()}_cia_aberta_{year}.zip'
        for document in ['DFP', 'ITR']
        for year in [2022, 2023]
    }
    assert len(list(output_dir.rglob('*.zip'))) == 4
    parquet_files = list(output_dir.rglob('*.parquet'))
    assert len(parquet_files) == (4 if automatic_extractor else 0)
    for parquet_file in parquet_files:
        assert pq.read_table(parquet_file).to_pylist() == [
            {'id': '1', 'value': '10'},
        ]
    assert 'Downloaded files count: 4' in capsys.readouterr().out


def test_cvm_corrupt_download_never_reports_success(
    tmp_path, monkeypatch, capsys
):
    install_fake_http_client(
        monkeypatch,
        lambda url: FakeResponse(
            url, [b'Invalid ZIP'], headers={'content-length': '11'}
        ),
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as error:
        _run_cvm_script(monkeypatch)

    assert error.value.code == 1
    output = capsys.readouterr()
    assert 'completed successfully' not in output.out
    assert 'DFP_2023' in output.err
    assert list((tmp_path / 'dados_cvm').rglob('*.parquet')) == []


@pytest.mark.parametrize('readme', ['README.md', 'README.en.md'])
def test_readme_python_examples_run_with_the_documented_paths(
    readme, cotahist_directory, tmp_path
):
    run_process(
        ['python', str(EXAMPLES_DIR / '02_quickstart_b3.py')],
        cwd=cotahist_directory.parent,
    )
    blocks = re.findall(
        r'```python\n(.*?)\n```',
        (EXAMPLES_DIR / readme).read_text(encoding='utf-8'),
        flags=re.DOTALL,
    )
    output = ''
    for index, block in enumerate(blocks):
        snippet = tmp_path / f'readme_example_{index}.py'
        snippet.write_text(block, encoding='utf-8')
        result = run_process(['python', str(snippet)], cwd=tmp_path)
        output += result.stdout
    table = pq.read_table(
        tmp_path / 'dados_b3' / 'cotacoes_acoes_2023.parquet'
    )

    assert len(blocks) == 2
    assert table.num_rows == 3
    assert set(table['tipo_mercado'].to_pylist()) == {'010', '020'}
    assert 'PETR4' in output
