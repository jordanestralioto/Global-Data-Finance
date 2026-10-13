"""Automatic extraction handling for CVM downloads."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from ....core import get_logger
from ....core.archive_safety import ArchiveSafetyLimits
from ....macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
    SecurityError,
)
from .download_validation import validate_parquet_files
from .extract import ParquetExtractorAdapterCVM
from .source_inventory import inspect_source, validate_output_inventory
from .write_ownership import exclusive_destination

logger = get_logger(__name__)


class ParquetExtractor(Protocol):
    """Minimal CVM extraction collaborator contract."""

    def extract(self, source_path: str, destination_path: str) -> None:
        """Convert one source ZIP into destination Parquet artifacts."""


def resolve_parquet_extractor(
    repository: ParquetExtractor | None,
    *,
    archive_limits: ArchiveSafetyLimits,
    allowed_unc_roots: Sequence[str],
) -> ParquetExtractor:
    """Return a supplied extractor or construct the default implementation."""
    if repository is not None:
        return repository

    return ParquetExtractorAdapterCVM(
        archive_limits=archive_limits,
        allowed_unc_roots=allowed_unc_roots,
    )


def extract_downloaded_file(
    file_extractor_repository: ParquetExtractor,
    filepath: str,
    dest_path: str,
    doc_name: str,
    year: str,
    *,
    archive_limits: ArchiveSafetyLimits | None = None,
) -> str | None:
    """Extract one archive, returning an error for loop-side aggregation."""
    document_key = f'{doc_name}_{year}'

    try:
        logger.info('Starting extraction for %s', document_key)
        with exclusive_destination(dest_path) as operations:
            source = Path(filepath)
            if source.parent == operations.snapshot.path:
                source = operations.bound_path(source)
            destination = operations.bound_path(operations.snapshot.path)
            inventory = inspect_source(
                source, destination, limits=archive_limits
            )
            file_extractor_repository.extract(filepath, dest_path)
            validate_output_inventory(source, destination, inventory)

            parquet_files = list(inventory.artifacts)
            if not all(path.is_file() for path in parquet_files):
                logger.warning(
                    'Extraction completed but no new or updated .parquet '
                    'files were found in %s. Keeping source ZIP: %s',
                    dest_path,
                    filepath,
                )
                return 'No parquet files generated after extraction'

            if not validate_parquet_files(
                parquet_files,
                doc_name,
                year,
                expected_archive_sha256=inventory.sha256,
                expected_members=inventory.artifacts,
            ):
                return 'Parquet validation failed: corrupted or empty files'

            logger.info(
                'Extraction completed for %s: %d parquet files created',
                document_key,
                len(parquet_files),
            )
            logger.info(
                'Retaining original CVM ZIP for reprocessing: %s', filepath
            )
            return None

    except DiskFullError as disk_err:
        logger.exception('Disk full during extraction of %s', document_key)
        logger.info(
            'Keeping ZIP after disk-full extraction failure: %s', filepath
        )
        return f'DiskFull: {disk_err}'

    except CorruptedZipError as zip_err:
        logger.exception(
            'Corrupted ZIP detected during extraction of %s', document_key
        )
        logger.info('Keeping corrupted ZIP for investigation: %s', filepath)
        return f'CorruptedZIP: {zip_err}'

    except ParquetWriteError as parquet_err:
        logger.exception(
            'Parquet write error during extraction of %s', document_key
        )
        logger.info('Keeping ZIP after Parquet write failure: %s', filepath)
        return f'ParquetWrite: {parquet_err}'

    except ExtractionError as extract_err:
        logger.exception('Extraction error for %s', document_key)
        logger.info('Keeping ZIP for manual investigation: %s', filepath)
        return f'ExtractionFailed: {extract_err}'

    except SecurityError:
        raise

    except Exception as unexpected_err:
        logger.error(
            f'Unexpected extraction error for {document_key}: '
            f'{type(unexpected_err).__name__}: {unexpected_err}',
            exc_info=True,
        )
        logger.info('Keeping ZIP for debugging: %s', filepath)
        return (
            f'UnexpectedError: {type(unexpected_err).__name__}: '
            f'{unexpected_err}'
        )
