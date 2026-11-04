"""Protect clone-ready B3 examples and their reproducible synthetic inputs."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copy2

import pyarrow.parquet as pq
import pytest

from examples.support import print_b3_preview
from globaldatafinance import HistoricalQuotesB3
from scripts import generate_example_cotahist
from scripts.cotahist_oracle import reconcile_sources
from scripts.cotahist_oracle.row_decoder import decode_quote
from scripts.cotahist_oracle.source_reader import (
    inspect_source,
    iter_bounded_lines,
    split_line_terminator,
)
from scripts.process_runner import run_process

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATES = {
    2022: {date(2022, 1, day) for day in (17, 18, 19)},
    2023: {date(2023, 1, day) for day in (16, 17, 18)},
}


def _source_quotes(year):
    """Read committed samples using offsets independent of the generator."""
    path = REPOSITORY_ROOT / 'cotahist_b3' / f'COTAHIST_A{year}.ZIP'
    source = inspect_source(path)
    quotes = []
    for number, raw in iter_bounded_lines(path, source.member):
        content, _terminator = split_line_terminator(raw)
        if content[:2] == b'01':
            quotes.append(
                decode_quote(
                    content,
                    source_name=path.name,
                    member=source.member,
                    year=year,
                    line_number=number,
                    content_sha256=source.content_sha256,
                )
            )
    return quotes


@pytest.mark.parametrize(
    ('script', 'output', 'years', 'markets', 'expected_rows'),
    [
        (
            '02_quickstart_b3.py',
            'cotacoes_acoes_2023.parquet',
            {2023},
            {'010', '020'},
            12,
        ),
        (
            '03_advanced_options_b3.py',
            'carteira_completa_2022_2023.parquet',
            {2022, 2023},
            {'010', '020', '070', '080'},
            36,
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
        day for year in years for day in SAMPLE_DATES[year]
    }
    assert table.to_pylist() == [
        row
        for year in sorted(years)
        for row in _source_quotes(year)
        if row['tipo_mercado'] in markets
    ]
    assert len(set(table['preco_fechamento'].to_pylist())) > 3
    assert len(table.schema) == 32
    assert (
        table.schema.metadata[b'globaldatafinance.b3.schema_version'] == b'2'
    )
    assert 'Quote preview (first 6 rows)' in result.stdout
    assert 'INDICE DEMO' in result.stdout
    assert 'BRBETAACNOR5' in result.stdout


@pytest.mark.parametrize('year', [2022, 2023])
def test_bundled_quotes_have_coherent_instruments_prices_and_maturities(year):
    """Different securities cannot inherit one stock's names or identifiers."""
    rows = _source_quotes(year)
    call_isin = 'BRALFAOPC004' if year == 2022 else 'BRALFAOPC012'
    put_isin = 'BRALFAOPV004' if year == 2022 else 'BRALFAOPV012'
    instruments = {
        ('ALFA4', '010'): ('ALFA', 'PN', 'BRALFAACNPR8'),
        ('BETA3', '010'): ('BETA', 'ON', 'BRBETAACNOR5'),
        ('INDX11', '010'): ('INDICE DEMO', 'CI', 'BRDEMOCTF000'),
        ('ALFA4F', '020'): ('ALFA', 'PN', 'BRALFAACNPR8'),
        ('ALFAA30', '070'): ('ALFA', 'PN', call_isin),
        ('ALFAM30', '080'): ('ALFA', 'PN', put_isin),
        ('ALFA4', '030'): ('ALFA', 'PN', 'BRALFAACNPR8'),
    }
    assert len(rows) == 21
    assert {row['data_pregao'] for row in rows} == SAMPLE_DATES[year]
    assert (
        len(
            {
                (row['data_pregao'], row['ticker'], row['tipo_mercado'])
                for row in rows
            }
        )
        == 21
    )
    for row in rows:
        assert row['data_pregao'].weekday() < 5
        assert (
            row['nome_resumido'],
            row['especificacao_papel'],
            row['codigo_isin'],
        ) == instruments[row['ticker'], row['tipo_mercado']]
        for field in ('preco_abertura', 'preco_fechamento', 'preco_medio'):
            assert row['preco_minimo'] <= row[field] <= row['preco_maximo']
        assert row['preco_minimo'] < row['preco_maximo']
        assert row['volume_total'] == (
            row['preco_medio'] * row['quantidade_total']
        )
        assert row['numero_negocios'] == 4
        assert row['moeda_referencia'] == 'R$'
        assert row['fator_cotacao'] == 1
        if row['tipo_mercado'] in {'070', '080', '030'}:
            assert row['data_vencimento'] > row['data_pregao']
            assert row['data_vencimento'].weekday() == 4
        else:
            assert row['data_vencimento'] is None
        if row['tipo_mercado'] in {'070', '080'}:
            assert row['preco_exercicio'] == Decimal('30.00')
        else:
            assert row['preco_exercicio'] == Decimal('0.00')
        if row['tipo_mercado'] == '030':
            assert (
                int(row['prazo_termo'])
                == (row['data_vencimento'] - row['data_pregao']).days
            )
        else:
            assert row['prazo_termo'] == ''
    for ticker, market in instruments:
        assert (
            len(
                {
                    row['preco_fechamento']
                    for row in rows
                    if row['ticker'] == ticker
                    and row['tipo_mercado'] == market
                }
            )
            == 3
        )


def test_sample_years_have_distinct_prices_and_option_contracts():
    """A second annual archive must not repeat the first year's values."""
    first_2022 = {
        (row['ticker'], row['tipo_mercado']): row
        for row in reversed(_source_quotes(2022))
    }
    first_2023 = {
        (row['ticker'], row['tipo_mercado']): row
        for row in reversed(_source_quotes(2023))
    }
    assert first_2023['ALFA4', '010']['preco_fechamento'] == Decimal('31.55')
    for key, earlier in first_2022.items():
        later = first_2023[key]
        assert later['preco_fechamento'] != earlier['preco_fechamento']
        if key[1] in {'070', '080'}:
            assert later['codigo_isin'] != earlier['codigo_isin']
        else:
            assert later['codigo_isin'] == earlier['codigo_isin']


@pytest.mark.parametrize('mode', ['fast', 'slow'])
def test_bundled_samples_reconcile_all_fields_and_bound_the_preview(
    mode, tmp_path, capsys
):
    """Both modes retain source identities, values, order and occurrences."""
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(REPOSITORY_ROOT / 'cotahist_b3'),
        assets_list=['todos'],
        initial_year=2022,
        last_year=2023,
        destination_path=str(tmp_path),
        output_filename='all_markets',
        processing_mode=mode,
        verbose=False,
    )
    assert result['success'] is True
    report = reconcile_sources(
        [
            REPOSITORY_ROOT / 'cotahist_b3' / f'COTAHIST_A{year}.ZIP'
            for year in (2022, 2023)
        ],
        Path(result['output_file']),
        public_result=dict(result),
    )
    assert report['verifiedRows'] == 42
    assert report['sourceCount'] == 2
    capsys.readouterr()

    print_b3_preview(result['output_file'], limit=2)

    preview = capsys.readouterr().out
    assert 'Quote preview (first 2 rows)' in preview
    assert len(preview.splitlines()) == 4
    assert 'ALFA4' in preview
    assert 'BETA3' in preview
    assert 'INDX11' not in preview


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
