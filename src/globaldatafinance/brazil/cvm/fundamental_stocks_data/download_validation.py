"""Validation helpers for CVM downloaded files."""

import zipfile
from pathlib import Path

from ....core import get_logger
from ....core.archive_safety import (
    ArchiveSafetyLimits,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError
from ....macro_infra import RequestsAdapter
from .parquet_validation import validate_parquet_data

logger = get_logger(__name__)


def validate_downloaded_file(
    filepath: str,
    expected_size: int | None = None,
    *,
    limits: ArchiveSafetyLimits | None = None,
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

        return has_valid_zip_contents(filepath, limits=limits)

    except OSError as error:
        logger.error(
            'Error validating file %s: %s', filepath, error, exc_info=True
        )
        return False


def find_parquet_files(dest_path: str) -> list[Path]:
    """Return all Parquet files below a destination directory."""
    return list(Path(dest_path).glob('**/*.parquet'))


def validate_parquet_files(
    parquet_files: list[Path],
    doc_name: str,
    year: str,
    *,
    expected_archive_sha256: str | None = None,
    expected_members: dict[Path, str] | None = None,
) -> bool:
    """Validate that Parquet files are readable and contain data."""
    import pyarrow.parquet as pq

    try:
        files = list(parquet_files)
    except (OSError, RuntimeError, TypeError) as error:
        logger.error(
            'Unable to enumerate parquet files for %s_%s: %s',
            doc_name,
            year,
            error,
            exc_info=True,
        )
        return False

    if not files:
        logger.error(
            'No parquet files were provided for %s_%s', doc_name, year
        )
        return False

    valid_files = 0
    for parquet_file in files:
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

            with pq.ParquetFile(
                parquet_file, page_checksum_verification=True
            ) as parquet:
                if expected_archive_sha256 is not None:
                    metadata_map = parquet.schema_arrow.metadata or {}
                    if metadata_map.get(
                        b'cvm.source-archive-sha256'
                    ) != expected_archive_sha256.encode(
                        'ascii'
                    ) or metadata_map.get(b'cvm.source-member') != (
                        expected_members or {}
                    )[parquet_file].encode('utf-8'):
                        raise ValueError(
                            'Parquet does not match its CVM source'
                        )
                parquet_metadata = parquet.metadata
                if (
                    parquet_metadata is None
                    or parquet_metadata.num_columns == 0
                ):
                    logger.error(
                        'Parquet has no usable metadata or columns: '
                        '%s for %s_%s',
                        parquet_file,
                        doc_name,
                        year,
                    )
                    return False
                validate_parquet_data(parquet, parquet_metadata.num_rows)

            valid_files += 1
            logger.debug(
                'Parquet validated: %s (%d rows, %d bytes)',
                parquet_file.name,
                parquet_metadata.num_rows,
                file_size,
            )

        except (OSError, ValueError) as error:
            logger.error(
                'Invalid parquet %s for %s_%s: %s: %s',
                parquet_file,
                doc_name,
                year,
                type(error).__name__,
                error,
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


def _has_valid_size(path: Path, expected_size: int) -> bool:
    actual_size = path.stat().st_size
    if expected_size <= 0 or actual_size != expected_size:
        logger.error(
            'File size mismatch for %s: expected %d bytes, got %d bytes',
            path,
            expected_size,
            actual_size,
        )
        return False

    logger.debug(
        'File size validation passed: %d bytes (expected %d)',
        actual_size,
        expected_size,
    )
    return True


def has_valid_zip_contents(
    filepath: str, *, limits: ArchiveSafetyLimits | None = None
) -> bool:
    """Check archive safety, member integrity, and CSV presence."""
    try:
        with zipfile.ZipFile(filepath, 'r') as zip_file:
            infos = validate_zip_archive(filepath, zip_file, limits=limits)
            if not infos:
                logger.error('Empty ZIP file: %s', filepath)
                return False

            validate_zip_crc_with_limits(
                filepath, zip_file, limits=limits, infos=infos
            )

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


def validate_download_options(
    max_concurrent: int, chunk_size: int, max_retries: int
) -> None:
    """Reject configurations that cannot execute bounded download attempts."""
    for name, value, minimum in (
        ('max_concurrent', max_concurrent, 1),
        ('chunk_size', chunk_size, 1),
        ('max_retries', max_retries, 0),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
        ):
            raise ValueError(f'{name} must be an integer >= {minimum}')


async def get_content_length(
    requests_adapter: RequestsAdapter, url: str
) -> int | None:
    """Read optional ZIP size metadata without hiding integrity failures."""
    try:
        response = await requests_adapter.async_head(url)
        content_length = response.headers.get('content-length')
        if content_length:
            size_bytes = int(content_length)
            logger.debug(
                'Content-Length for %s: %.2f MB',
                url,
                size_bytes / 1024 / 1024,
            )
            return size_bytes
        logger.debug('No Content-Length header for %s', url)
        return None
    except Exception:
        logger.warning(
            'Failed to get Content-Length for %s', url, exc_info=True
        )
        return None
