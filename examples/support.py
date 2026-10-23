"""Shared output naming, summaries and diagnostics for editable examples."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Never

from globaldatafinance import ExtractionResultB3
from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
)


def _fail_result(message: str, errors: dict[str, str]) -> Never:
    """Report an incomplete result and stop before showing success."""
    sys.stderr.write(message + '\n')
    for name, diagnostic in errors.items():
        sys.stderr.write(f'  • {name}: {diagnostic}\n')
    raise SystemExit(1)


def year_label(initial_year: int, last_year: int) -> str:
    """Return a single year or range for a Parquet output basename."""
    if initial_year == last_year:
        return str(initial_year)
    return f'{initial_year}_{last_year}'


def print_cvm_summary(
    result: DownloadResultCVM, *, destination_path: str
) -> None:
    """Check for completed downloads before reporting the CVM result."""
    if result.has_errors() or result.success_count_downloads == 0:
        _fail_result(
            '✗ CVM download did not complete successfully.',
            result.failed_downloads,
        )
    sys.stdout.write(
        '✓ Download completed successfully!\n'
        f'  Output directory: {destination_path}\n'
        f'  Downloaded files count: {result.success_count_downloads}\n'
    )


def print_b3_summary(result: ExtractionResultB3, *, verbose: bool) -> None:
    """Check for usable quotes before reporting the B3 result."""
    output_file = result['output_file']
    output_path = Path(output_file) if output_file else None
    if not (
        result['success']
        and result['total_files'] > 0
        and result['total_records'] > 0
        and output_path is not None
        and output_path.is_file()
        and output_path.stat().st_size > 0
    ):
        _fail_result(
            '✗ B3 extraction did not produce a non-empty Parquet file.',
            result['errors'],
        )
    lines = [
        '✓ Extraction completed successfully!',
        f'  Generated Parquet file at: {result["output_file"]}',
        f'  Total processed files: {result["total_files"]}',
        f'  Quote records: {result["total_records"]:,}',
    ]
    if verbose:
        lines.extend(
            [
                f'  Selected markets: {", ".join(result["assets"])}',
                f'  Processing mode: {result["processing_mode"]}',
                f'  Elapsed seconds: {result["elapsed_time"]:.2f}',
            ]
        )
    sys.stdout.write('\n'.join(lines) + '\n')


def print_b3_preview(output_file: str, *, limit: int = 6) -> None:
    """Show a bounded quote preview with source identity and market context."""
    import pyarrow.parquet as pq

    if limit <= 0:
        raise ValueError('Preview limit must be positive')
    columns = [
        'data_pregao',
        'ticker',
        'tipo_mercado',
        'nome_resumido',
        'preco_fechamento',
        'codigo_isin',
    ]
    with pq.ParquetFile(output_file) as parquet:
        batches = parquet.iter_batches(batch_size=limit, columns=columns)
        batch = next(batches, None)
    if batch is None:
        return
    lines = [
        f'  Quote preview (first {batch.num_rows} rows):',
        '  Date       | Ticker       | Market | Name         | Close | ISIN',
    ]
    for row in batch.to_pylist():
        lines.append(
            f'  {row["data_pregao"]} | {row["ticker"]:<12} | '
            f'{row["tipo_mercado"]:>6} | {row["nome_resumido"]:<12} | '
            f'{row["preco_fechamento"]:.2f} | {row["codigo_isin"]}'
        )
    sys.stdout.write('\n'.join(lines) + '\n')


def run_example(main: Callable[[], None]) -> None:
    """Report expected input failures with a diagnostic and nonzero exit."""
    if len(sys.argv) > 1:
        sys.stderr.write(
            'Edit SETTINGS in the example file, then run it without '
            'command-line options.\n'
        )
        raise SystemExit(2)
    try:
        main()
    except (B3Error, CvmError, ValueError, OSError) as error:
        sys.stderr.write(f'Example failed: {error}\n')
        raise SystemExit(1) from error
