"""Synchronous validation, promotion, and extraction for one CVM download."""

import asyncio
from collections.abc import Callable
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ....core import get_logger
from .download_extraction import extract_downloaded_file

logger = get_logger(__name__)
_FINALIZER_POLL_INTERVAL = 0.005


class _ParquetExtractor(Protocol):
    """Minimal CVM extraction contract used during download finalization."""

    def extract(self, source_path: str, destination_path: str) -> None:
        """Convert one source ZIP into destination Parquet artifacts."""


class _DownloadedFileValidator(Protocol):
    """Validate a staged archive without changing its contents."""

    def __call__(self, filepath: str, expected_size: int | None) -> bool:
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
    expected_size: int | None,
    *,
    automatic_extractor: bool,
    file_extractor_repository: _ParquetExtractor | None,
    validate_file: _DownloadedFileValidator,
    cleanup_file: Callable[[str], None],
) -> DownloadFinalizationResultCVM:
    """Validate and publish a staged ZIP, then optionally extract it."""
    document_key = f'{doc_name}_{year}'
    promoted = False
    owns_staging = staging_path != final_path

    try:
        if not validate_file(str(staging_path), expected_size):
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
            staging_path.replace(final_path)
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

    if automatic_extractor:
        if file_extractor_repository is None:
            raise RuntimeError(
                'Automatic extraction requires a CVM Parquet extractor'
            )
        extraction_error = extract_downloaded_file(
            file_extractor_repository=file_extractor_repository,
            filepath=str(final_path),
            dest_path=dest_path,
            doc_name=doc_name,
            year=year,
            cleanup_file=cleanup_file,
        )
        if extraction_error is not None:
            return DownloadFinalizationResultCVM(
                succeeded=False,
                error_message=extraction_error,
            )
        return DownloadFinalizationResultCVM(succeeded=True)

    logger.info('✓ Downloaded %s (extraction disabled)', document_key)
    return DownloadFinalizationResultCVM(succeeded=True)
