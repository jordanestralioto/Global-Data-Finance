"""Example 03: Advanced B3 Extraction Options (Multiple Assets and Fast Mode).

This example demonstrates how to filter multiple asset types (Stocks, ETFs,
and Options) from local COTAHIST files, select a range of years, and use
high-performance 'fast' mode.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from examples.cli import parse_arguments, run_example, year_label
    from examples.result_validation import require_b3_output
else:
    from cli import parse_arguments, run_example, year_label
    from result_validation import require_b3_output

from globaldatafinance import HistoricalQuotesB3


def main(argv: Sequence[str] | None = None) -> None:
    """Run the advanced B3 options example."""
    args = parse_arguments(
        'Extract stocks, ETFs and options from local B3 COTAHIST files.',
        source='b3',
        argv=argv,
    )
    b3 = HistoricalQuotesB3()
    print('Starting advanced B3 extraction (Stocks, ETFs, Options)...')
    result = b3.extract(
        path_of_docs=args.path_of_docs,
        assets_list=['ações', 'etf', 'opções'],
        initial_year=args.initial_year,
        last_year=args.last_year,
        destination_path=args.destination_path,
        output_filename=(
            'carteira_completa_'
            f'{year_label(args.initial_year, args.last_year)}'
        ),
        processing_mode=args.processing_mode,
        verbose=False,
    )
    require_b3_output(result)
    print('✓ Advanced extraction completed successfully!')
    print(f'  Generated Parquet file at: {result["output_file"]}')
    print(f'  Total processed files: {result["total_files"]}')
    print(f'  Quote records: {result["total_records"]:,}')


if __name__ == '__main__':
    run_example(main)
