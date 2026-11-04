"""Generate the small synthetic COTAHIST archives bundled with the examples."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_corpus.containers import select_b3_container
from tests.support.builders import write_cotahist_txt

SAMPLES_DIRECTORY = Path(__file__).resolve().parents[1] / 'cotahist_b3'
SAMPLE_YEARS = (2022, 2023)
SAMPLE_START_DATES = {2022: date(2022, 1, 17), 2023: date(2023, 1, 16)}


@dataclass(frozen=True)
class SampleInstrument:
    """Describe a fictional instrument without shared test defaults."""

    ticker: str
    market: str
    bdi: str
    name: str
    specification: str
    isin: str
    price_cents: int
    quantity: int
    strike_cents: int = 0
    isin_2023: str = ''


SAMPLE_INSTRUMENTS = (
    SampleInstrument(
        'ALFA4', '010', '02', 'ALFA', 'PN', 'BRALFAACNPR8', 3000, 1200
    ),
    SampleInstrument(
        'BETA3', '010', '02', 'BETA', 'ON', 'BRBETAACNOR5', 7200, 800
    ),
    SampleInstrument(
        'INDX11', '010', '02', 'INDICE DEMO', 'CI', 'BRDEMOCTF000', 10500, 400
    ),
    SampleInstrument(
        'ALFA4F', '020', '96', 'ALFA', 'PN', 'BRALFAACNPR8', 3000, 12
    ),
    SampleInstrument(
        'ALFAA30',
        '070',
        '78',
        'ALFA',
        'PN',
        'BRALFAOPC004',
        120,
        400,
        strike_cents=3000,
        isin_2023='BRALFAOPC012',
    ),
    SampleInstrument(
        'ALFAM30',
        '080',
        '82',
        'ALFA',
        'PN',
        'BRALFAOPV004',
        90,
        400,
        strike_cents=3000,
        isin_2023='BRALFAOPV012',
    ),
    SampleInstrument(
        'ALFA4', '030', '62', 'ALFA', 'PN', 'BRALFAACNPR8', 3050, 400
    ),
)


def _sample_maturity(market: str, trading_date: date) -> date | None:
    """Assign future maturities only to options and forward contracts."""
    start = SAMPLE_START_DATES[trading_date.year]
    if market in {'070', '080'}:
        return start + timedelta(days=4)
    if market == '030':
        return start + timedelta(days=32)
    return None


def _quote_fields(
    instrument: SampleInstrument, trading_date: date, day_index: int
) -> dict[str, str | int]:
    """Model four equal-size trades with exact prices and volume in cents."""
    options = instrument.market in {'070', '080'}
    step = 3 if options else 15
    average = (
        instrument.price_cents
        + (trading_date.year - SAMPLE_YEARS[0]) * step * 10
        + day_index * step
    )
    quantity_step = 4 if instrument.market == '020' else 400
    quantity = instrument.quantity + day_index * quantity_step
    maturity = _sample_maturity(instrument.market, trading_date)
    isin = (
        instrument.isin_2023
        if trading_date.year == 2023 and instrument.isin_2023
        else instrument.isin
    )
    return {
        'tipo_registro': '01',
        'data_pregao': trading_date.strftime('%Y%m%d'),
        'codigo_bdi': instrument.bdi,
        'ticker': instrument.ticker,
        'tipo_mercado': instrument.market,
        'nome_resumido': instrument.name,
        'especificacao_papel': instrument.specification,
        'prazo_termo': (
            f'{(maturity - trading_date).days:03d}'
            if maturity is not None and instrument.market == '030'
            else ''
        ),
        'moeda_referencia': 'R$',
        'preco_abertura': average - 10,
        'preco_maximo': average + 10,
        'preco_minimo': average - 10,
        'preco_medio': average,
        'preco_fechamento': average + 5,
        'melhor_oferta_compra': average + 4,
        'melhor_oferta_venda': average + 6,
        'numero_negocios': 4,
        'quantidade_total': quantity,
        'volume_total': average * quantity,
        'preco_exercicio': instrument.strike_cents,
        'indicador_correcao': '0',
        'data_vencimento': (
            maturity.strftime('%Y%m%d') if maturity else '00000000'
        ),
        'fator_cotacao': 1,
        'preco_exercicio_pontos': 0,
        'codigo_isin': isin,
        'numero_distribuicao': 1,
    }


def _build_quote(
    instrument: SampleInstrument, trading_date: date, day_index: int
) -> str:
    """Serialize complete sample values using the canonical source widths."""
    from globaldatafinance.brazil.b3_data.historical_quotes.layout import (
        B3_QUOTATION_LAYOUT,
        B3_QUOTATION_WIDTH,
    )

    values = _quote_fields(instrument, trading_date, day_index)
    record = [' '] * B3_QUOTATION_WIDTH
    for field in B3_QUOTATION_LAYOUT:
        if (
            field.start is None
            or field.stop is None
            or field.kind == 'original_record'
        ):
            continue
        value = values[field.name]
        width = field.stop - field.start
        rendered = (
            str(value).zfill(width)
            if isinstance(value, int)
            else value.ljust(width)
        )
        if len(rendered) != width:
            raise ValueError(f'Sample field {field.name} exceeds its width')
        record[field.start : field.stop] = rendered
    return ''.join(record)


def build_samples() -> dict[str, bytes]:
    """Build valid synthetic documents with fixed ZIP member timestamps."""
    archives = {}
    with TemporaryDirectory(prefix='gdf-example-cotahist-') as temporary:
        for year in SAMPLE_YEARS:
            source = write_cotahist_txt(
                Path(temporary),
                year=year,
                records=[
                    _build_quote(
                        instrument,
                        SAMPLE_START_DATES[year] + timedelta(days=day_index),
                        day_index,
                    )
                    for day_index in range(3)
                    for instrument in SAMPLE_INSTRUMENTS
                ],
            )
            archive = select_b3_container(source, 'zip')
            archives[archive.name] = archive.read_bytes()
    return archives


def check_samples(directory: Path) -> tuple[str, ...]:
    """Report missing or changed generated archives without writing them."""
    return tuple(
        name
        for name, expected in build_samples().items()
        if not (directory / name).is_file()
        or (directory / name).read_bytes() != expected
    )


def write_samples(directory: Path) -> None:
    """Replace only the two reserved synthetic example ZIPs."""
    archives = build_samples()
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in archives.items():
        (directory / name).write_bytes(content)


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate the bundled inputs or verify their canonical contents."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--check', action='store_true', help='Check samples without writing'
    )
    args = parser.parse_args(argv)
    if args.check:
        mismatches = check_samples(SAMPLES_DIRECTORY)
        if mismatches:
            sys.stderr.write(
                'Missing or changed COTAHIST samples: '
                + ', '.join(mismatches)
                + '\n'
            )
            return 1
        sys.stdout.write('Bundled COTAHIST samples match the generator.\n')
        return 0
    write_samples(SAMPLES_DIRECTORY)
    sys.stdout.write(f'Generated synthetic samples in {SAMPLES_DIRECTORY}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
