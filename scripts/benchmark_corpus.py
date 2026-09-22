"""Deterministic CVM and B3 corpora used by the benchmark coordinator."""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.benchmark_support import (
    DEFAULT_ROWS,
    ScenarioInput,
    directory_digest,
    logical_digest,
    sha256_file,
)

_ANNUAL_B3_YEARS = tuple(range(2000, 2027))


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


def write_b3_txt(path: Path, rows: int, *, start_index: int = 0) -> None:
    """Create a deterministic official-name COTAHIST text input."""
    with path.open('w', encoding='latin-1', newline='') as target:
        target.write('00COTAHIST BENCHMARK\n')
        for index in range(start_index, start_index + rows):
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


def _prepare_b3_multi(
    root: Path,
    rows: int,
    source_count: int | None,
    worker_limit: int | None,
    backend: str,
    processing_mode: str,
) -> ScenarioInput:
    """Generate the synthetic multi-file B3 input directory.

    Args:
        root: Temporary root directory where corpus files are placed.
        rows: Total synthetic quotation rows to distribute across files.
        source_count: Optional override for number of generated files.
        worker_limit: Optional limit on worker processes or threads.
        backend: Execution backend ('thread' or 'process').
        processing_mode: Ingestion mode ('fast' or 'slow').

    Returns:
        Fully configured ScenarioInput for the b3_multi_4x25k scenario.
    """
    scenario_dir = root / 'b3_multi_4x25k'
    scenario_dir.mkdir(exist_ok=True)
    count = source_count if source_count is not None else 4
    if count < 1:
        raise ValueError(f'source_count must be at least 1, got {count}')
    if count > rows:
        raise ValueError(
            f'source_count ({count}) cannot be greater than rows ({rows})'
        )
    current_year = datetime.now(UTC).year
    max_allowed_years = current_year - 2020
    if count > max_allowed_years:
        raise ValueError(
            f'source_count ({count}) exceeds maximum allowed years from '
            f'2021 to {current_year} ({max_allowed_years})'
        )
    effective_limit = (
        worker_limit
        if worker_limit is not None
        else min(count, os.cpu_count() or 1)
    )
    if effective_limit < 1:
        raise ValueError(
            f'worker_limit must be at least 1, got {effective_limit}'
        )
    base, rem = divmod(rows, count)
    cur_start = 0
    for idx in range(count):
        rows_this_file = base + (1 if idx < rem else 0)
        year = 2021 + idx
        write_b3_txt(
            scenario_dir / f'COTAHIST_A{year}.TXT',
            rows_this_file,
            start_index=cur_start,
        )
        cur_start += rows_this_file
    return ScenarioInput(
        'b3_multi_4x25k',
        scenario_dir,
        rows,
        directory_digest(scenario_dir),
        'GD0000000000',
        f'GD{rows - 1:010d}'[-12:],
        expected_b3_digest(rows),
        executor_backend=backend,
        processing_mode=processing_mode,
        source_count=count,
        worker_limit=effective_limit,
    )


def prepare_input(
    scenario: str,
    root: Path,
    rows_override: int | None,
    annual_path: Path | None,
    backend: str = 'thread',
    processing_mode: str = 'fast',
    source_count: int | None = None,
    worker_limit: int | None = None,
) -> ScenarioInput:
    """Generate or locate the one source input for a selected scenario."""
    if scenario in {'import_root', 'runtime_footprint'}:
        return ScenarioInput(
            scenario,
            None,
            0,
            '',
            executor_backend=backend,
            processing_mode=processing_mode,
        )
    if scenario == 'b3_annual':
        if source_count is not None:
            raise ValueError(
                'source_count is not supported for b3_annual; it always '
                f'uses all {len(_ANNUAL_B3_YEARS)} source files'
            )
        if worker_limit is not None and worker_limit < 1:
            raise ValueError(
                f'worker_limit must be at least 1, got {worker_limit}'
            )
        effective_sources = len(_ANNUAL_B3_YEARS)
        effective_limit = (
            worker_limit
            if worker_limit is not None
            else min(effective_sources, os.cpu_count() or 1)
        )
        if annual_path is None or not annual_corpus_available(annual_path):
            return ScenarioInput(
                scenario,
                None,
                0,
                '',
                executor_backend=backend,
                processing_mode=processing_mode,
                source_count=effective_sources,
                worker_limit=effective_limit,
            )
        return ScenarioInput(
            scenario,
            annual_path,
            0,
            directory_digest(annual_path),
            expected_digest=expected_b3_annual_digest(annual_path),
            executor_backend=backend,
            processing_mode=processing_mode,
            source_count=effective_sources,
            worker_limit=effective_limit,
        )
    rows = rows_override or DEFAULT_ROWS[scenario]
    if scenario == 'b3_multi_4x25k':
        return _prepare_b3_multi(
            root,
            rows,
            source_count,
            worker_limit,
            backend,
            processing_mode,
        )
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
            executor_backend=backend,
            processing_mode=processing_mode,
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
        executor_backend=backend,
        processing_mode=processing_mode,
    )


def annual_corpus_available(path: Path | None) -> bool:
    """Require the complete 27-ZIP annual corpus before timing it."""
    if path is None or not path.is_dir():
        return False
    return len(_annual_b3_source_paths(path)) == len(_ANNUAL_B3_YEARS)


def expected_b3_annual_digest(path: Path) -> str:
    """Build the full typed expectation from the annual source corpus."""
    sources = _annual_b3_source_paths(path)
    if len(sources) != len(_ANNUAL_B3_YEARS):
        raise ValueError(
            f'B3 annual benchmark requires all {len(_ANNUAL_B3_YEARS)} '
            'official ZIP files'
        )
    return logical_digest(_annual_b3_rows(sources))


def _annual_b3_source_paths(path: Path) -> tuple[Path, ...]:
    """Return canonical annual ZIP paths in the same order as extraction."""
    paths_by_name = {
        item.name.casefold(): item for item in path.iterdir() if item.is_file()
    }
    return tuple(
        paths_by_name[f'cotahist_a{year}.zip']
        for year in _ANNUAL_B3_YEARS
        if f'cotahist_a{year}.zip' in paths_by_name
    )


def _annual_b3_rows(paths: tuple[Path, ...]) -> Iterator[dict[str, Any]]:
    """Yield canonical typed equity rows directly from official annual ZIPs."""
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        assets,
        cotahist_parser,
        zip_reader,
    )

    target_tpmerc_codes = (
        assets.AvailableAssetsServiceB3.get_tpmerc_codes_for_assets({'ações'})
    )
    parser = cotahist_parser.CotahistParserB3()
    reader = zip_reader.ZipFileReaderB3()
    for path in paths:
        for line, context in reader.iter_lines(str(path)):
            if record := parser.parse_line(line, target_tpmerc_codes, context):
                yield record
