"""Run the opt-in, live CVM download and extraction benchmark."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyarrow.parquet as pq

from globaldatafinance import FundamentalStocksDataCVM
from scripts.benchmark_support import RssSampler

BASELINE_SECONDS = 906.85
BASELINE_RSS_MIB = 333.91


def main(output_dir: Path) -> int:
    """Measure the complete 2010-2026 CVM workflow on live source data."""
    if (
        not output_dir.is_dir()
        or output_dir.is_symlink()
        or any(output_dir.iterdir())
    ):
        print('Output directory must exist and be empty')
        return 2
    client = FundamentalStocksDataCVM()

    print('Running live CVM download and extraction for 2010-2026')
    print(f'Output directory: {output_dir.resolve()}')
    sampler = RssSampler()
    sampler.start()
    started = time.perf_counter()
    try:
        result = client.download(
            destination_path=str(output_dir),
            list_docs=[],
            initial_year=2010,
            last_year=2026,
            automatic_extractor=True,
        )
    finally:
        sampler.stop()

    elapsed_seconds = time.perf_counter() - started
    parquet_files = list(output_dir.rglob('*.parquet'))
    total_rows = sum(
        pq.ParquetFile(path).metadata.num_rows for path in parquet_files
    )
    total_bytes = sum(path.stat().st_size for path in parquet_files)
    peak_rss_mib = sampler.parent_peak_bytes / (1024 * 1024)
    difference_percent = (
        (elapsed_seconds - BASELINE_SECONDS) / BASELINE_SECONDS * 100
    )

    print(f'Elapsed time: {elapsed_seconds:.2f} s')
    print(f'Peak parent RSS: {peak_rss_mib:.2f} MiB')
    print(f'Successful ZIPs: {result.success_count_downloads}')
    print(f'Parquet files: {len(parquet_files)}')
    print(f'Rows extracted: {total_rows:,}')
    print(f'Parquet size: {total_bytes / (1024 * 1024):.2f} MiB')
    print(f'Failed downloads: {result.error_count_downloads}')
    print(f'Time versus baseline: {difference_percent:+.1f}%')
    print(f'Historical baseline peak RSS: {BASELINE_RSS_MIB:.2f} MiB')
    for document_key, error in result.failed_downloads.items():
        print(f'  {document_key}: {error}')
    return 1 if result.error_count_downloads else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    raise SystemExit(main(parser.parse_args().output_dir))
