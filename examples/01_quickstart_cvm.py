"""Example 01: Quickstart with CVM (DFP Financial Statements).

This example demonstrates how to download and extract standardized financial
statements (DFP) for Brazilian public companies directly into Parquet format.
"""

import sys
from pathlib import Path


def main() -> None:
    """Run the CVM quickstart example."""
    # Ensure examples import repository code rather than the installed package.
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / 'src'))
    sys.path.insert(0, str(repo_root))

    from examples.result_validation import require_cvm_download_success
    from globaldatafinance import FundamentalStocksDataCVM

    # 1. Initialize the CVM public facade
    cvm = FundamentalStocksDataCVM()

    output_dir = './dados_cvm'

    # 2. Execute download with automatic conversion to Parquet
    print('Starting CVM DFP data download and extraction...')
    resultado = cvm.download(
        destination_path=output_dir,
        list_docs=['DFP'],
        initial_year=2023,
        last_year=2023,
        automatic_extractor=True,
    )

    # 3. Display final result
    require_cvm_download_success(resultado)
    print('✓ Download completed successfully!')
    print(f'  Parquet files directory: {output_dir}')
    print(f'  Downloaded files count: {resultado.success_count_downloads}')


if __name__ == '__main__':
    main()
