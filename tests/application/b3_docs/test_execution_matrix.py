"""Reconcile supported sources, processing modes, and executor backends."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from scripts.cotahist_oracle import reconcile_sources
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
@pytest.mark.parametrize('mode', ['fast', 'slow'])
@pytest.mark.parametrize('backend', ['thread', 'process'])
def test_all_execution_combinations_preserve_selected_occurrences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    mode: str,
    backend: str,
) -> None:
    """Sources retain duplicates, block lots, and unknown numeric markets."""
    sources = tmp_path / 'sources'
    sources.mkdir()
    write_source = (
        write_cotahist_zip if extension == 'ZIP' else write_cotahist_txt
    )
    paths = []
    for year in (2023, 2024):
        duplicate = build_cotahist_record(year=year, ticker='PETR4')
        paths.append(
            write_source(
                sources,
                year=year,
                records=[
                    duplicate,
                    build_cotahist_record(
                        year=year, ticker='BLOCK', market='021'
                    ),
                    build_cotahist_record(
                        year=year, ticker='UNKNOWN', market='999'
                    ),
                    duplicate,
                ],
            )
        )
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', backend)
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', '2')
    facade = HistoricalQuotesB3()

    result = facade.extract(
        path_of_docs=str(sources),
        initial_year=2023,
        last_year=2024,
        destination_path=str(tmp_path / 'output'),
        processing_mode=mode,
        verbose=False,
    )

    assert result['success'] is True
    assert result['total_files'] == result['success_count'] == 2
    assert result['total_records'] == 8
    assert result['error_count'] == 0
    assert result['integrity']['intentional_exclusions'] == 0
    expected_backend = (
        'process' if mode == 'fast' and backend == 'process' else 'thread'
    )
    assert facade._last_phase_timings['effective_backend'] == expected_backend
    assert facade._last_phase_timings['effective_worker_limit'] == (
        2 if mode == 'fast' else 1
    )
    reconciliation = reconcile_sources(
        paths,
        Path(result['output_file']),
        public_result=dict(result),
        batch_size=1,
    )
    assert reconciliation['verifiedRows'] == 8
    assert reconciliation['marketCounts'] == {'010': 4, '021': 2, '999': 2}
    assert reconciliation['unknownMarketCounts'] == {'999': 2}
    assert reconciliation['blockLotRowsByYear'] == {2023: 1, 2024: 1}
    assert reconciliation['previousTwentyFieldsEqual'] is True


@pytest.mark.parametrize(
    ('assets', 'selected'),
    [
        (['ações'], {'010', '020'}),
        (['etf'], {'010', '020'}),
        (['opções'], {'070', '080'}),
        (['termo'], {'030'}),
        (['exercicio_opcoes'], {'012', '013'}),
        (['forward'], {'050', '060'}),
        (['leilao'], {'017'}),
        (['lote_bloco'], {'021'}),
        (['ações', 'etf', 'ações'], {'010', '020'}),
        (['lote_bloco', 'lote_bloco'], {'021'}),
        (['todos'], None),
        (['TODOS', 'ações'], None),
        (None, None),
    ],
)
def test_public_classes_and_complete_union_select_each_occurrence_once(
    tmp_path: Path,
    assets: list[str] | None,
    selected: set[str] | None,
) -> None:
    """Class overlaps and repetitions cannot duplicate or lose source rows."""
    codes = (
        '010',
        '020',
        '030',
        '050',
        '060',
        '070',
        '080',
        '012',
        '013',
        '017',
        '021',
        '999',
    )
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(market=code, ticker=f'TICK{index}')
            for index, code in enumerate(codes)
        ],
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        assets_list=assets,
        initial_year=2024,
        last_year=2024,
        destination_path=str(tmp_path / 'output'),
        verbose=False,
    )

    expected = [code for code in codes if selected is None or code in selected]
    assert result['success'] is True
    assert result['total_records'] == len(expected)
    assert pq.read_table(result['output_file'])[
        'tipo_mercado'
    ].to_pylist() == (expected)
    assert result['integrity']['raw_quotes'] == len(codes)
    assert result['integrity']['selected_quotes'] == len(expected)
    assert result['integrity']['intentional_exclusions'] == len(codes) - len(
        expected
    )
    assert result['integrity']['complete_market_selection'] is (
        selected is None
    )


@pytest.mark.parametrize('mode', ['fast', 'slow'])
def test_source_text_and_original_bytes_survive_both_conversion_paths(
    tmp_path: Path, mode: str
) -> None:
    """Accents, quotes, internal spaces, and zero codes remain exact."""
    source = list(build_cotahist_record(ticker='AÇÃOM', market='021'))
    for start, stop, value in [
        (10, 12, 'A '),
        (27, 39, 'AÇÃO  "A"'),
        (39, 49, 'PN " B"'),
        (49, 52, '003'),
        (52, 56, 'US$ '),
        (230, 242, 'BR" AÇ 123'),
    ]:
        source[start:stop] = list(value.ljust(stop - start))
    record = ''.join(source)
    path = write_cotahist_txt(tmp_path, year=2024, records=[record])

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(tmp_path / 'output'),
        processing_mode=mode,
        verbose=False,
    )

    assert result['success'] is True
    row = pq.read_table(result['output_file']).to_pylist()[0]
    assert {
        name: row[name]
        for name in (
            'codigo_bdi',
            'ticker',
            'nome_resumido',
            'especificacao_papel',
            'prazo_termo',
            'moeda_referencia',
            'codigo_isin',
        )
    } == {
        'codigo_bdi': 'A',
        'ticker': 'AÇÃOM',
        'nome_resumido': 'AÇÃO  "A"',
        'especificacao_papel': 'PN " B"',
        'prazo_termo': '003',
        'moeda_referencia': 'US$',
        'codigo_isin': 'BR" AÇ 123',
    }
    assert row['registro_original'] == record.encode('latin-1')
    assert (
        reconcile_sources(
            [path], Path(result['output_file']), public_result=dict(result)
        )['verifiedRows']
        == 1
    )
