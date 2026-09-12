"""Validation helpers for CVM downloaded files."""

import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from ....core import get_logger
from ....core.archive_safety import (
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError

logger = get_logger(__name__)


def validate_downloaded_file(
    filepath: str, expected_size: int | None = None
) -> bool:
    """Validate that a downloaded ZIP is present, complete, and readable."""
    try:
        path = Path(filepath)

        if not path.exists():
            logger.error('Downloaded file does not exist: %s', filepath)
            return False

        if expected_size is not None and not _has_valid_size(
            path, expected_size
        ):
            return False

        return _has_valid_zip_contents(filepath)

    except Exception as e:
        logger.error(
            'Error validating file %s: %s', filepath, e, exc_info=True
        )
        return False


def find_parquet_files(dest_path: str) -> list[Path]:
    """Return all Parquet files below a destination directory."""
    return list(Path(dest_path).glob('**/*.parquet'))


def validate_parquet_files(
    parquet_files: list[Path], doc_name: str, year: str
) -> bool:
    """Validate that parquet files are readable and contain data."""
    if not parquet_files:
        logger.error(
            'No parquet files were provided for %s_%s', doc_name, year
        )
        return False

    try:
        valid_files = 0
        for parquet_file in parquet_files:
            try:
                file_size = parquet_file.stat().st_size
                if file_size == 0:
                    logger.error(
                        'Empty parquet file (0 bytes): %s for %s_%s',
                        parquet_file,
                        doc_name,
                        year,
                    )
                    return False

                parquet_metadata = pq.ParquetFile(parquet_file).metadata
                if parquet_metadata is None:
                    logger.error(
                        'Parquet metadata is unavailable: %s for %s_%s',
                        parquet_file,
                        doc_name,
                        year,
                    )
                    return False

                if parquet_metadata.num_columns == 0:
                    logger.error(
                        'Parquet file has no columns: %s for %s_%s',
                        parquet_file,
                        doc_name,
                        year,
                    )
                    return False

                valid_files += 1
                logger.debug(
                    'Parquet validated: %s (%d rows, %d bytes)',
                    parquet_file.name,
                    parquet_metadata.num_rows,
                    file_size,
                )

            except Exception as e:
                logger.error(
                    'Invalid parquet %s for %s_%s: %s: %s',
                    parquet_file,
                    doc_name,
                    year,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                return False

        logger.info(
            'All %d parquet files validated for %s_%s',
            valid_files,
            doc_name,
            year,
        )
        return True

    except Exception as e:
        logger.error(
            'Unexpected error validating parquets: %s', e, exc_info=True
        )
        return False


def _has_valid_size(path: Path, expected_size: int) -> bool:
    actual_size = path.stat().st_size
    size_diff = abs(actual_size - expected_size)
    size_diff_pct = (
        (size_diff / expected_size) * 100 if expected_size > 0 else 0
    )

    if size_diff_pct > 5.0:
        logger.error(
            'File size mismatch for %s: expected %d bytes, got %d bytes '
            '(%.1f%% difference)',
            path,
            expected_size,
            actual_size,
            size_diff_pct,
        )
        return False

    logger.debug(
        'File size validation passed: %d bytes (expected %d, diff %.2f%%)',
        actual_size,
        expected_size,
        size_diff_pct,
    )
    return True


def _has_valid_zip_contents(filepath: str) -> bool:
    try:
        with zipfile.ZipFile(filepath, 'r') as zip_file:
            infos = validate_zip_archive(filepath, zip_file)
            if not infos:
                logger.error('Empty ZIP file: %s', filepath)
                return False

            validate_zip_crc_with_limits(filepath, zip_file, infos=infos)

            csv_files = [
                info.filename
                for info in infos
                if not info.is_dir() and info.filename.lower().endswith('.csv')
            ]
            if not csv_files:
                logger.error(
                    'No CSV files in ZIP: %s. Files found: %s%s',
                    filepath,
                    ', '.join(info.filename for info in infos[:5]),
                    '...' if len(infos) > 5 else '',
                )
                return False

    except (CorruptedZipError, OSError, zipfile.BadZipFile):
        logger.exception('Invalid or unsafe ZIP file %s', filepath)
        return False

    logger.debug('File validation passed: %s', filepath)
    return True
