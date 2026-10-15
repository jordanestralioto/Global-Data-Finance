"""Prepare local fixtures and verify flows from an isolated installation."""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
import zipfile
from pathlib import Path


def prepare_inputs(root: Path) -> None:
    """Reuse source-owned builders before leaving the source checkout."""
    from tests.support.builders import (
        build_cotahist_record,
        write_cotahist_txt,
        write_cotahist_zip,
    )

    cvm = root / 'cvm'
    cvm.mkdir(parents=True)
    with zipfile.ZipFile(cvm / 'source.zip', 'w') as archive:
        archive.writestr('data.csv', 'id;name\n1;first\n2;second\n')
    for kind, builder in [
        ('zip', write_cotahist_zip),
        ('txt', write_cotahist_txt),
    ]:
        destination = root / kind
        destination.mkdir()
        builder(
            destination,
            year=2024,
            records=[
                build_cotahist_record(ticker='PETR4'),
                build_cotahist_record(ticker='VALE3'),
            ],
        )


def check_installation(root: Path, environment: Path, version: str) -> None:
    """Exercise installed package exports and real CVM/B3 filesystem flows."""
    import pyarrow.parquet as pq

    import globaldatafinance
    from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
        ParquetExtractorAdapterCVM,
    )

    assert Path(sys.prefix).resolve() == environment.resolve()
    assert (
        Path(globaldatafinance.__file__)
        .resolve()
        .is_relative_to(environment.resolve())
    )
    assert importlib.metadata.version('globaldatafinance') == version
    assert set(globaldatafinance.__all__) == {
        'ExtractionResultB3',
        'FundamentalStocksDataCVM',
        'HistoricalQuotesB3',
    }
    assert (
        'DFP'
        in globaldatafinance.FundamentalStocksDataCVM().get_available_docs()
    )
    source = root / 'cvm' / 'source.zip'
    before = source.read_bytes()
    ParquetExtractorAdapterCVM().extract(str(source), str(source.parent))
    assert pq.read_table(source.parent / 'data.parquet').to_pylist() == [
        {'id': '1', 'name': 'first'},
        {'id': '2', 'name': 'second'},
    ]
    assert source.read_bytes() == before
    for kind in ('zip', 'txt'):
        source = next((root / kind).glob('COTAHIST_A2024.*'))
        before = source.read_bytes()
        for mode in ('fast', 'slow'):
            result = globaldatafinance.HistoricalQuotesB3().extract(
                path_of_docs=str(root / kind),
                initial_year=2024,
                last_year=2024,
                processing_mode=mode,
                output_filename=f'quotes-{mode}.parquet',
                verbose=False,
            )
            assert result['success'] is True, result
            table = pq.read_table(result['output_file'])
            assert table.num_rows == 2
            assert sorted(table['ticker'].to_pylist()) == ['PETR4', 'VALE3']
            assert source.read_bytes() == before


def main() -> None:
    """Prepare inputs normally; run checks with Python isolated mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--environment', type=Path)
    parser.add_argument('--expected-version')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare_inputs(args.root)
    else:
        if args.environment is None or args.expected_version is None:
            parser.error('check requires --environment and --expected-version')
        check_installation(args.root, args.environment, args.expected_version)


if __name__ == '__main__':
    main()
