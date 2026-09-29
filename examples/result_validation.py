"""Validate example result objects before reporting successful runs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

from globaldatafinance import ExtractionResultB3


class CvmDownloadResult(Protocol):
    """Fields used by the CVM quickstart result check."""

    @property
    def error_count_downloads(self) -> int:
        """Return the number of failed document downloads."""
        ...

    @property
    def failed_downloads(self) -> dict[str, str]:
        """Return diagnostic messages keyed by the failed document."""
        ...

    @property
    def success_count_downloads(self) -> int:
        """Return the number of successful document downloads."""
        ...


def require_cvm_download_success(result: CvmDownloadResult) -> None:
    """Stop the example when downloads failed or returned no files."""
    if (
        result.error_count_downloads == 0
        and result.success_count_downloads > 0
    ):
        return
    sys.stderr.write('✗ CVM download did not complete successfully.\n')
    for document, message in result.failed_downloads.items():
        sys.stderr.write(f'  • {document}: {message}\n')
    raise SystemExit(1)


def require_b3_output(result: ExtractionResultB3) -> None:
    """Stop the example unless B3 produced a non-empty Parquet artifact."""
    output_file = result['output_file']
    output_path = Path(output_file) if output_file else None
    if (
        result['success']
        and result['total_files'] > 0
        and result['total_records'] > 0
        and output_path is not None
        and output_path.is_file()
        and output_path.stat().st_size > 0
    ):
        return
    sys.stderr.write(
        '✗ B3 extraction did not produce a non-empty Parquet file.\n'
    )
    for file_name, message in result['errors'].items():
        sys.stderr.write(f'  • {file_name}: {message}\n')
    raise SystemExit(1)
