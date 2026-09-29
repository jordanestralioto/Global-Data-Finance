"""Example 02: Quickstart with B3 (Historical Stock Quotes).

This example demonstrates how to read and extract historical stock quotes
from local COTAHIST files (e.g. COTAHIST_A2023.ZIP or .TXT) saved in
'path_of_docs' and generate a consolidated Parquet file.
"""

import sys
from pathlib import Path


def main() -> None:
    """Run the B3 quickstart example."""
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
        path_of_docs='./cotahist_b3',  # Folder containing local COTAHIST files
        assets_list=['ações'],
        initial_year=2023,
        last_year=2023,
        destination_path='./dados_b3',
        output_filename='cotacoes_acoes_2023',
    )

    # 3. Display final result
    require_b3_output(resultado)
    print('✓ Extraction completed successfully!')
    print(f'  Generated Parquet file at: {resultado["output_file"]}')
    print(f'  Total processed files: {resultado["total_files"]}')


if __name__ == '__main__':
    main()
