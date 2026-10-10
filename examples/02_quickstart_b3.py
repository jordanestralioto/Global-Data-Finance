"""Example 02: Quickstart with B3 (Historical Stock Quotes).

This example demonstrates how to read and extract historical stock quotes
from local COTAHIST files (e.g. COTAHIST_A2023.ZIP or .TXT) saved in
'path_of_docs' and generate a consolidated Parquet file.
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
    """Run the B3 quickstart example."""
    args = parse_arguments(
        'Extract stock quotes from local B3 COTAHIST files to Parquet.',
        source='b3',
        argv=argv,
    )
    b3 = HistoricalQuotesB3()
    print('Starting B3 stock quotes extraction...')
    result = b3.extract(
        path_of_docs=args.path_of_docs,
        assets_list=['ações'],
        initial_year=args.initial_year,
        last_year=args.last_year,
        destination_path=args.destination_path,
        output_filename=(
            f'cotacoes_acoes_{year_label(args.initial_year, args.last_year)}'
        ),
        processing_mode=args.processing_mode,
        verbose=False,
    )
    require_b3_output(result)
    print('✓ Extraction completed successfully!')
    print(f'  Generated Parquet file at: {result["output_file"]}')
    print(f'  Total processed files: {result["total_files"]}')
    print(f'  Quote records: {result["total_records"]:,}')


if __name__ == '__main__':
    run_example(main)
