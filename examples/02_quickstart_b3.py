"""Example 02: Quickstart with B3 (Historical Stock Quotes).

This example demonstrates how to read and extract historical stock quotes
from local COTAHIST files (e.g. COTAHIST_A2023.ZIP or .TXT) saved in
'path_of_docs' and generate a consolidated Parquet file.
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Run the B3 quickstart example."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path-of-docs', default='./cotahist_b3')
    parser.add_argument('--initial-year', type=int, default=2023)
    parser.add_argument('--last-year', type=int, default=2023)
    parser.add_argument('--destination-path', default='./dados_b3')
    args = parser.parse_args()
    year_label = (
        str(args.initial_year)
        if args.initial_year == args.last_year
        else f'{args.initial_year}_{args.last_year}'
    )
    # Ensure examples import repository code rather than the installed package.
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / 'src'))
    sys.path.insert(0, str(repo_root))

    from examples.result_validation import require_b3_output
    from globaldatafinance import HistoricalQuotesB3

    # 1. Initialize the B3 public facade
    b3 = HistoricalQuotesB3()

    # 2. Extract stock quotes from local COTAHIST files
    print('Starting B3 stock quotes extraction...')
    resultado = b3.extract(
        path_of_docs=args.path_of_docs,
        assets_list=['ações'],
        initial_year=args.initial_year,
        last_year=args.last_year,
        destination_path=args.destination_path,
        output_filename=f'cotacoes_acoes_{year_label}',
    )

    # 3. Display final result
    require_b3_output(resultado)
    print('✓ Extraction completed successfully!')
    print(f'  Generated Parquet file at: {resultado["output_file"]}')
    print(f'  Total processed files: {resultado["total_files"]}')


if __name__ == '__main__':
    main()
