"""Extract multiple B3 markets. Edit SETTINGS, then run this file."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from examples import support
else:
    import support

from globaldatafinance import HistoricalQuotesB3

# SETTINGS: change the values here. The README explains each option.
INITIAL_YEAR = 2010
LAST_YEAR = 2026
PATH_OF_DOCS = (
    '/mnt/f4ec9d54-a0c2-4385-9e66-533d8f9307ae/Downloads/'
    'Databases/dados_bolsa_br/COTAHIST'
)
DESTINATION_PATH = './dados_b3'
ASSETS = ['ações', 'etf', 'opções']  # Use ['todos'] for every market.
OUTPUT_NAME = 'carteira_completa'  # Years are added automatically.
PROCESSING_MODE = 'fast'  # Use 'slow' to reduce memory usage.
VERBOSE = True  # Extra summary details; file progress is always shown.


def main() -> None:
    """Run the advanced B3 options example."""
    b3 = HistoricalQuotesB3()
    years = support.year_label(INITIAL_YEAR, LAST_YEAR)
    print('Starting B3 extraction...')
    result = b3.extract(
        path_of_docs=PATH_OF_DOCS,
        assets_list=ASSETS,
        initial_year=INITIAL_YEAR,
        last_year=LAST_YEAR,
        destination_path=DESTINATION_PATH,
        output_filename=f'{OUTPUT_NAME}_{years}',
        processing_mode=PROCESSING_MODE,
        verbose=False,
    )
    support.print_b3_summary(result, verbose=VERBOSE)


if __name__ == '__main__':
    support.run_example(main)
