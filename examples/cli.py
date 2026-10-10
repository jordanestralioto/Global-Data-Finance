"""Shared command-line options and diagnostics for the runnable examples."""

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Literal

from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
)


def parse_arguments(
    description: str,
    *,
    source: Literal['cvm', 'b3'],
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse explicit paths and an inclusive year range for one example."""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--initial-year',
        type=int,
        default=2023,
        help='First year to process (inclusive).',
    )
    parser.add_argument(
        '--last-year',
        type=int,
        default=argparse.SUPPRESS,
        help='Last year to process (inclusive); defaults to --initial-year.',
    )
    parser.add_argument(
        '--destination-path',
        default=f'./dados_{source}',
        help='Directory for the generated Parquet files.',
    )
    if source == 'b3':
        parser.add_argument(
            '--path-of-docs',
            default='./cotahist_b3',
            help='Directory containing local COTAHIST ZIP or TXT files.',
        )
        parser.add_argument(
            '--processing-mode',
            choices=['fast', 'slow'],
            default='fast',
            help='Use fast for throughput or slow for lower memory usage.',
        )
    args = parser.parse_args(argv)
    args.last_year = getattr(args, 'last_year', args.initial_year)
    if args.last_year < args.initial_year:
        parser.error(
            '--last-year must be greater than or equal to --initial-year.'
        )
    return args


def year_label(initial_year: int, last_year: int) -> str:
    """Return a single year or range for a Parquet output basename."""
    if initial_year == last_year:
        return str(initial_year)
    return f'{initial_year}_{last_year}'


def run_example(main: Callable[[], None]) -> None:
    """Report expected input failures with a diagnostic and nonzero exit."""
    try:
        main()
    except (B3Error, CvmError, ValueError, OSError) as error:
        sys.stderr.write(f'Example failed: {error}\n')
        raise SystemExit(1) from error
