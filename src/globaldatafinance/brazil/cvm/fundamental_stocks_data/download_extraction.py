"""Automatic extraction handling for CVM downloads."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from ....core import get_logger, remove_file
from ....core.archive_safety import ArchiveSafetyLimits
from ....macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)
from .download_validation import find_parquet_files, validate_parquet_files

logger = get_logger(__name__)

ParquetArtifactStateCVM = dict[Path, tuple[int, int]]


class ParquetExtractor(Protocol):
    """Minimal deferred CVM extraction collaborator contract."""

    def extract(self, source_path: str, destination_path: str) -> None:
        """Convert one source ZIP into destination Parquet artifacts."""


def resolve_parquet_extractor(
    repository: ParquetExtractor | None,
    *,
    archive_limits: ArchiveSafetyLimits,
    allowed_unc_roots: Sequence[str],
) -> ParquetExtractor:
    """Return a supplied extractor or lazily create the CVM implementation."""
    if repository is not None:
        return repository

    from .extract import ParquetExtractorAdapterCVM

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
    cleanup_file: Callable[[str], None] = remove_file,
) -> str | None:
    """Extract one archive, returning an error for loop-side aggregation."""
    document_key = f'{doc_name}_{year}'

    try:
        logger.info('Starting extraction for %s', document_key)
        parquet_artifacts_before = _snapshot_parquet_artifacts(dest_path)
        file_extractor_repository.extract(filepath, dest_path)

        parquet_files = _find_current_extraction_parquets(
            dest_path,
            parquet_artifacts_before,
        )
        if not parquet_files:
            logger.warning(
                'Extraction completed but no new or updated .parquet files '
                'were found in %s. Keeping source ZIP: %s',
                dest_path,
                filepath,
            )
            return 'No parquet files generated after extraction'

        if not validate_parquet_files(parquet_files, doc_name, year):
            return 'Parquet validation failed: corrupted or empty files'

        logger.info(
            'Extraction completed for %s: %d parquet files created',
            document_key,
            len(parquet_files),
        )
        cleanup_file(filepath)
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


def _snapshot_parquet_artifacts(dest_path: str) -> ParquetArtifactStateCVM:
    """Capture the parquet state present before one extraction attempt."""
    artifacts: ParquetArtifactStateCVM = {}
    for parquet_file in find_parquet_files(dest_path):
        try:
            stat = parquet_file.stat()
        except OSError as exc:
            logger.warning(
                'Could not snapshot existing parquet %s: %s', parquet_file, exc
            )
            continue
        artifacts[parquet_file.resolve()] = (stat.st_size, stat.st_mtime_ns)
    return artifacts


def _find_current_extraction_parquets(
    dest_path: str,
    previous_artifacts: ParquetArtifactStateCVM,
) -> list[Path]:
    """Return parquet files created or overwritten by the current attempt."""
    changed_artifacts: list[Path] = []
    for parquet_file in find_parquet_files(dest_path):
        try:
            resolved_path = parquet_file.resolve()
            stat = parquet_file.stat()
        except OSError as exc:
            logger.warning(
                'Could not inspect extracted parquet %s: %s', parquet_file, exc
            )
            continue

        current_state = (stat.st_size, stat.st_mtime_ns)
        if previous_artifacts.get(resolved_path) != current_state:
            changed_artifacts.append(parquet_file)

    return changed_artifacts
