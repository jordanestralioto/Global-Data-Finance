"""Extract B3 stock quotes. Edit the SETTINGS block, then run this file."""

from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from examples import support
else:
    import support

from globaldatafinance import HistoricalQuotesB3

# SETTINGS: change the values here. The README explains each option.
INITIAL_YEAR = 2023
LAST_YEAR = 2023
PATH_OF_DOCS = './cotahist_b3'  # Folder with COTAHIST_AYYYY.ZIP or .TXT files.
DESTINATION_PATH = './dados_b3'
ASSETS = ['ações']  # Market groups; use ['todos'] for every market.
OUTPUT_NAME = 'cotacoes_acoes'  # The selected years are added automatically.
PROCESSING_MODE = 'fast'  # Use 'slow' to reduce memory usage.
VERBOSE = False  # Extra summary details; file progress is always shown.


def main() -> None:
    """Run the B3 quickstart example."""
    b3 = HistoricalQuotesB3()
    years = support.year_label(INITIAL_YEAR, LAST_YEAR)
    print('Starting B3 stock quotes extraction...')
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
