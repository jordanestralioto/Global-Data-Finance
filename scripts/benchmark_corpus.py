"""Deterministic CVM and B3 corpora used by the benchmark coordinator."""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.benchmark_support import (
    DEFAULT_ROWS,
    ScenarioInput,
    directory_digest,
    logical_digest,
    sha256_file,
)

_ANNUAL_B3_YEARS = tuple(range(2008, 2025))


def write_cvm_zip(path: Path, rows: int, *, long_text: bool = False) -> None:
    """Create one deterministic CVM ZIP with a late numeric-type change."""
    member = 'dfp_cia_aberta_2024.csv'
    text_width = 8_000 if long_text else 250
    payload = ('GlobalDataFinance-' * ((text_width // 18) + 1))[:text_width]
    compression = zipfile.ZIP_STORED if long_text else zipfile.ZIP_DEFLATED
    with (
        zipfile.ZipFile(path, 'w', compression=compression) as archive,
        archive.open(member, 'w') as raw,
    ):
        raw.write(b'identificador;valor;descricao\n')
        for index in range(rows):
            value = '1.25' if index == rows - 1 else str(index)
            line = f'{index};{value};{payload}{index:08d}\n'
            raw.write(line.encode('utf-8'))


def b3_record(index: int) -> str:
    """Build one exact-width, selected type-01 COTAHIST record."""
    record = [' '] * 245

    def fill(start: int, end: int, value: str, *, right: bool = False) -> None:
        width = end - start
        formatted = value.rjust(width) if right else value.ljust(width)
        record[start:end] = formatted[:width]

    fill(0, 2, '01')
    fill(2, 10, '20240115')
    fill(10, 12, '02')
    fill(12, 24, f'GD{index:010d}'[-12:])
    fill(24, 27, '010')
    fill(27, 39, f'GLOBAL {index % 1000:04d}')
    fill(39, 49, 'ON')
    for start, end, value in (
        (56, 69, 1_000_000 + index),
        (69, 82, 1_000_200 + index),
        (82, 95, 999_800 + index),
        (95, 108, 1_000_100 + index),
        (108, 121, 1_000_050 + index),
        (121, 134, 1_000_000 + index),
        (134, 147, 1_000_100 + index),
        (170, 188, 10_000_000 + index),
    ):
        fill(start, end, str(value), right=True)
    fill(147, 152, str((index % 99_999) + 1), right=True)
    fill(152, 170, str(1_000_000 + index), right=True)
    fill(202, 210, '00000000')
    fill(210, 217, '1', right=True)
    fill(230, 242, f'BRGD{index:08d}'[-12:])
    fill(242, 245, str((index % 999) + 1), right=True)
    return ''.join(record)


def write_b3_txt(path: Path, rows: int) -> None:
    """Create a deterministic official-name COTAHIST text input."""
    with path.open('w', encoding='latin-1', newline='') as target:
        target.write('00COTAHIST BENCHMARK\n')
        for index in range(rows):
            target.write(b3_record(index))
            target.write('\n')
        target.write('99COTAHIST BENCHMARK\n')


def expected_cvm_digest(rows: int, *, long_text: bool = False) -> str:
    """Return the typed digest expected from one generated CVM corpus."""
    text_width = 8_000 if long_text else 250
    payload = ('GlobalDataFinance-' * ((text_width // 18) + 1))[:text_width]
    return logical_digest(
        {
            'identificador': index,
            'valor': 1.25 if index == rows - 1 else float(index),
            'descricao': f'{payload}{index:08d}',
        }
        for index in range(rows)
    )


def expected_b3_digest(rows: int) -> str:
    """Return the typed digest expected from one generated B3 corpus."""
    return logical_digest(_expected_b3_record(index) for index in range(rows))


def _expected_b3_record(index: int) -> dict[str, object]:
    """Build the logical values represented by :func:`b3_record`."""
    return {
        'data_pregao': date(2024, 1, 15),
        'codigo_bdi': '02',
        'ticker': f'GD{index:010d}'[-12:],
        'tipo_mercado': '010',
        'nome_resumido': f'GLOBAL {index % 1000:04d}',
        'especificacao_papel': 'ON',
        'preco_abertura': Decimal(1_000_000 + index).scaleb(-2),
        'preco_maximo': Decimal(1_000_200 + index).scaleb(-2),
        'preco_minimo': Decimal(999_800 + index).scaleb(-2),
        'preco_medio': Decimal(1_000_100 + index).scaleb(-2),
        'preco_fechamento': Decimal(1_000_050 + index).scaleb(-2),
        'melhor_oferta_compra': Decimal(1_000_000 + index).scaleb(-2),
        'melhor_oferta_venda': Decimal(1_000_100 + index).scaleb(-2),
        'numero_negocios': (index % 99_999) + 1,
        'quantidade_total': 1_000_000 + index,
        'volume_total': Decimal(10_000_000 + index).scaleb(-2),
        'data_vencimento': None,
        'fator_cotacao': 1,
        'codigo_isin': f'BRGD{index:08d}'[-12:],
        'numero_distribuicao': (index % 999) + 1,
    }


def prepare_input(
    scenario: str,
    root: Path,
    rows_override: int | None,
    annual_path: Path | None,
) -> ScenarioInput:
    """Generate or locate the one source input for a selected scenario."""
    if scenario in {'import_root', 'runtime_footprint'}:
        return ScenarioInput(scenario, None, 0, '')
    if scenario == 'b3_annual':
        if annual_path is None or not annual_corpus_available(annual_path):
            return ScenarioInput(scenario, None, 0, '')
        return ScenarioInput(
            scenario,
            annual_path,
            0,
            directory_digest(annual_path),
        )
    rows = rows_override or DEFAULT_ROWS[scenario]
    if scenario.startswith('cvm'):
        source = root / f'{scenario}.zip'
        write_cvm_zip(source, rows, long_text=scenario == 'cvm_text')
        return ScenarioInput(
            scenario,
            source,
            rows,
            sha256_file(source),
            '0',
            str(rows - 1),
            expected_cvm_digest(rows, long_text=scenario == 'cvm_text'),
        )
    source = root / 'COTAHIST_A2024.TXT'
    write_b3_txt(source, rows)
    return ScenarioInput(
        scenario,
        source,
        rows,
        sha256_file(source),
        'GD0000000000',
        f'GD{rows - 1:010d}'[-12:],
        expected_b3_digest(rows),
    )


def annual_corpus_available(path: Path | None) -> bool:
    """Require the complete 17-ZIP annual corpus before timing it."""
    if path is None or not path.is_dir():
        return False
    available_names = {
        item.name.casefold() for item in path.iterdir() if item.is_file()
    }
    return all(
        f'cotahist_a{year}.zip' in available_names for year in _ANNUAL_B3_YEARS
    )
