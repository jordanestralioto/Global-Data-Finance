"""Download CVM documents. Edit the SETTINGS block, then run this file."""

from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from examples import support
else:
    import support

from globaldatafinance import FundamentalStocksDataCVM

# SETTINGS: change the values here. The README explains each option.
INITIAL_YEAR = 2010
LAST_YEAR = 2026
DESTINATION_PATH = './dados_cvm'
DOCUMENTS: list[str] = []  # All types; use ['DFP'] for annual statements.
AUTOMATIC_EXTRACTOR = False  # Set True to also convert the ZIPs to Parquet.


def main() -> None:
    """Run the CVM quickstart example."""
    cvm = FundamentalStocksDataCVM()
    print('Starting CVM download...')
    result = cvm.download(
        destination_path=DESTINATION_PATH,
        list_docs=DOCUMENTS,
        initial_year=INITIAL_YEAR,
        last_year=LAST_YEAR,
        automatic_extractor=AUTOMATIC_EXTRACTOR,
    )
    support.print_cvm_summary(result, destination_path=DESTINATION_PATH)


if __name__ == '__main__':
    support.run_example(main)
