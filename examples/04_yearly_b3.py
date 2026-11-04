"""Save B3 stock quotes in yearly folders. Edit SETTINGS, then run."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from examples import support
else:
    import support

from globaldatafinance import HistoricalQuotesB3

# SETTINGS: change the values here. The README explains each option.
INITIAL_YEAR = 2022
LAST_YEAR = 2023
PATH_OF_DOCS = './cotahist_b3'  # Fictional samples; see README for real data.
DESTINATION_PATH = './dados_b3/cotacoes_acoes_por_ano'
ASSETS = ['ações']  # Market groups; use ['todos'] for every market.
OUTPUT_NAME = 'cotacoes_acoes'  # Each filename receives its own year.
PROCESSING_MODE = 'fast'  # Use 'slow' to reduce memory usage.
VERBOSE = False  # Extra summary details; file progress is always shown.


def main() -> None:
    """Extract each selected year independently into its own directory."""
    if LAST_YEAR < INITIAL_YEAR:
        raise ValueError(
            'LAST_YEAR must be greater than or equal to INITIAL_YEAR'
        )

    b3 = HistoricalQuotesB3()
    for year in range(INITIAL_YEAR, LAST_YEAR + 1):
        print(f'Starting B3 stock quotes extraction for {year}...')
        result = b3.extract(
            path_of_docs=PATH_OF_DOCS,
            assets_list=ASSETS,
            initial_year=year,
            last_year=year,
            destination_path=str(Path(DESTINATION_PATH) / str(year)),
            output_filename=f'{OUTPUT_NAME}_{year}',
            processing_mode=PROCESSING_MODE,
            verbose=False,
        )
        support.print_b3_summary(result, verbose=VERBOSE)
        support.print_b3_preview(result['output_file'])


if __name__ == '__main__':
    support.run_example(main)
