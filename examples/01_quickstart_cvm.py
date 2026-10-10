"""Example 01: Quickstart with CVM (DFP Financial Statements).

This example demonstrates how to download and extract standardized financial
statements (DFP) for Brazilian public companies directly into Parquet format.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from examples.cli import parse_arguments, run_example
    from examples.result_validation import require_cvm_download_success
else:
    from cli import parse_arguments, run_example
    from result_validation import require_cvm_download_success

from globaldatafinance import FundamentalStocksDataCVM


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CVM quickstart example."""
    args = parse_arguments(
        'Download CVM DFP financial statements and convert them to Parquet.',
        source='cvm',
        argv=argv,
    )
    cvm = FundamentalStocksDataCVM()
    print('Starting CVM DFP data download and extraction...')
    result = cvm.download(
        destination_path=args.destination_path,
        list_docs=['DFP'],
        initial_year=args.initial_year,
        last_year=args.last_year,
        automatic_extractor=True,
    )
    require_cvm_download_success(result)
    print('✓ Download completed successfully!')
    print(f'  Parquet files directory: {args.destination_path}')
    print(f'  Downloaded files count: {result.success_count_downloads}')


if __name__ == '__main__':
    run_example(main)
