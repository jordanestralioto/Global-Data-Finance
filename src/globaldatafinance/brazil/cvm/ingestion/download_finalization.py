"""Synchronous validation, promotion, and extraction for one CVM download."""

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

from ....core import get_logger
from ....core.archive_safety import ArchiveSafetyLimits
from ....macro_exceptions import ExtractionError, PathIsNotDirectoryError
from ....macro_infra.transactional_publication.durability import (
    sync_directory,
    sync_file,
)
from .destination_io import (
    DestinationFileOperationsCVM,
    DownloadDestinationSnapshot,
    assert_download_destination_unchanged,
)
from .download_extraction import ParquetExtractor, extract_downloaded_file
from .write_ownership import exclusive_destination

logger = get_logger(__name__)
_FINALIZER_POLL_INTERVAL = 0.005


class _DownloadedFileValidator(Protocol):
    """Validate a staged archive without changing its contents."""

    def __call__(self, filepath: str) -> bool:
        """Return whether the staged archive is complete and safe."""


@dataclass(frozen=True)
class DownloadFinalizationResultCVM:
    """One completed download finalization result for loop-side aggregation."""

    succeeded: bool
    error_message: str | None = None


async def _wait_for_finalizer(
    worker: Future[DownloadFinalizationResultCVM],
) -> DownloadFinalizationResultCVM:
    """Wait without requiring a worker thread to wake the event loop."""
    while not worker.done():
        await asyncio.sleep(_FINALIZER_POLL_INTERVAL)
    return worker.result()


async def run_download_finalizer(
    executor: Executor,
    finalization_lock: asyncio.Lock,
    finalizer: Callable[[], DownloadFinalizationResultCVM],
) -> DownloadFinalizationResultCVM:
    """Run blocking finalization while keeping cancellation write-safe."""
    async with finalization_lock:
        worker = executor.submit(finalizer)
        try:
            return await _wait_for_finalizer(worker)
        except asyncio.CancelledError:
            while not worker.done():
                try:
                    await asyncio.sleep(_FINALIZER_POLL_INTERVAL)
                except asyncio.CancelledError:
                    continue
            raise


def finalize_downloaded_file(
    staging_path: Path,
    final_path: Path,
    dest_path: str,
    doc_name: str,
    year: str,
    *,
    automatic_extractor: bool,
    file_extractor_repository: ParquetExtractor | None,
    validate_file: _DownloadedFileValidator,
    cleanup_file: Callable[[str], None],
    allowed_unc_roots: Sequence[str] | None = None,
    archive_limits: ArchiveSafetyLimits | None = None,
    expected_destination: DownloadDestinationSnapshot | None = None,
) -> DownloadFinalizationResultCVM:
    """Own the destination before publishing or extracting a staged ZIP."""
    try:
        with exclusive_destination(
            dest_path,
            allowed_unc_roots=allowed_unc_roots,
            expected_destination=expected_destination,
        ) as operations:
            return _finalize_owned_download(
                staging_path,
                final_path,
                doc_name,
                year,
                automatic_extractor=automatic_extractor,
                file_extractor_repository=file_extractor_repository,
                validate_file=validate_file,
                cleanup_file=cleanup_file,
                archive_limits=archive_limits,
                operations=operations,
            )
    except (ExtractionError, PathIsNotDirectoryError, OSError) as error:
        logger.error(
            'Failed to finalize %s_%s: %s',
            doc_name,
            year,
            error,
            exc_info=True,
        )
        if staging_path != final_path:
            cleanup_file(str(staging_path))
        return DownloadFinalizationResultCVM(
            succeeded=False,
            error_message=str(error),
        )


def _finalize_owned_download(
    staging_path: Path,
    final_path: Path,
    doc_name: str,
    year: str,
    *,
    automatic_extractor: bool,
    file_extractor_repository: ParquetExtractor | None,
    validate_file: _DownloadedFileValidator,
    cleanup_file: Callable[[str], None],
    archive_limits: ArchiveSafetyLimits | None,
    operations: DestinationFileOperationsCVM,
) -> DownloadFinalizationResultCVM:
    """Validate and publish one ZIP while holding its destination lease."""
    document_key = f'{doc_name}_{year}'
    extract: Callable[[], str | None] | None = None
    if automatic_extractor:
        if file_extractor_repository is None:
            raise RuntimeError(
                'Automatic extraction requires a CVM Parquet extractor'
            )
        extract = partial(
            extract_downloaded_file,
            file_extractor_repository=file_extractor_repository,
            filepath=str(final_path),
            dest_path=str(operations.snapshot.path),
            doc_name=doc_name,
            year=year,
            archive_limits=archive_limits,
        )
    promoted = False
    owns_staging = staging_path != final_path

    try:
        if not validate_file(str(staging_path)):
            logger.error(
                'Downloaded file validation failed for %s: %s',
                document_key,
                staging_path,
            )
            return DownloadFinalizationResultCVM(
                succeeded=False,
                error_message=(
                    'Downloaded file corrupted, incomplete, or invalid ZIP'
                ),
            )

        try:
            assert_download_destination_unchanged(
                final_path.parent.resolve(), operations.snapshot
            )
            sync_file(operations, staging_path)
            operations.replace(staging_path, final_path)
            sync_directory(operations, final_path.parent)
        except OSError as promotion_error:
            logger.error(
                'Failed to promote downloaded file for %s: %s',
                document_key,
                promotion_error,
                exc_info=True,
            )
            return DownloadFinalizationResultCVM(
                succeeded=False,
                error_message=(
                    'Downloaded file promotion failed: '
                    f'{type(promotion_error).__name__}: {promotion_error}'
                ),
            )

        promoted = True
    finally:
        if owns_staging and not promoted:
            cleanup_file(str(staging_path))

    assert_download_destination_unchanged(
        final_path.parent.resolve(), operations.snapshot
    )
    if extract is not None:
        extraction_error = extract()
        assert_download_destination_unchanged(
            final_path.parent.resolve(), operations.snapshot
        )
        if extraction_error is not None:
            return DownloadFinalizationResultCVM(
                succeeded=False,
                error_message=extraction_error,
            )
        return DownloadFinalizationResultCVM(succeeded=True)

    logger.info('✓ Downloaded %s (extraction disabled)', document_key)
    return DownloadFinalizationResultCVM(succeeded=True)
