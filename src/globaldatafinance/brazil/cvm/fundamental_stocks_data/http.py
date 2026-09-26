"""Async HTTP download adapter for CVM ZIP files."""

import asyncio
from collections.abc import Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import partial
from pathlib import Path

import httpx

from ....core import (
    RetryStrategy,
    SimpleProgressBar,
    get_logger,
    remove_file,
)
from ....core.archive_safety import ArchiveSafetyLimits
from ....core.config import PathSafetySettings
from ....macro_exceptions import DownloadTimeoutError, NetworkError
from ....macro_infra import RequestsAdapter
from .core import DownloadResultCVM
from .download_extraction import (
    _ParquetExtractor,
    resolve_parquet_extractor,
)
from .download_finalization import (
    finalize_downloaded_file,
    run_download_finalizer,
)
from .download_paths import build_download_target_path
from .download_validation import validate_downloaded_file

logger = get_logger(__name__)

DownloadTaskCVM = tuple[str, str, str, str]
_TIMEOUT_ERRORS = (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)
_NETWORK_ERRORS = (httpx.RequestError, httpx.HTTPStatusError, ConnectionError)


class AsyncDownloadAdapterCVM:
    """Download CVM ZIP files with retry, integrity checks, and extraction."""

    def __init__(
        self,
        file_extractor_repository: _ParquetExtractor | None,
        max_concurrent: int = 10,
        chunk_size: int = 8192,
        timeout: float = 180.0,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 120.0,
        backoff_multiplier: float = 2.0,
        http2: bool = True,
        automatic_extractor: bool = False,
        user_agent: str | None = None,
        follow_redirects: bool = True,
        archive_limits: ArchiveSafetyLimits | None = None,
        allowed_unc_roots: Sequence[str] | None = None,
    ):
        """Initialize the adapter and preserve httpx defaults."""
        self.file_extractor_repository = file_extractor_repository
        self.max_concurrent = max_concurrent
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.automatic_extractor = automatic_extractor
        if archive_limits is None:
            archive_limits = ArchiveSafetyLimits.from_environment()
        self.archive_limits = archive_limits
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        headers = None if user_agent is None else {'User-Agent': user_agent}
        self.requests_adapter = RequestsAdapter(
            timeout=timeout,
            http2=http2,
            verify=True,
            max_redirects=5,
            follow_redirects=follow_redirects,
            default_headers=headers,
        )
        self.retry_strategy = RetryStrategy(
            initial_backoff=initial_backoff,
            max_backoff=max_backoff,
            multiplier=backoff_multiplier,
        )

    def download_docs(
        self,
        tasks: list[DownloadTaskCVM],
        *,
        automatic_extractor: bool | None = None,
    ) -> DownloadResultCVM:
        """Synchronously download documents using an owned event loop."""
        return asyncio.run(
            self.async_download_docs(
                tasks, automatic_extractor=automatic_extractor
            )
        )

    async def async_download_docs(
        self,
        tasks: list[DownloadTaskCVM],
        *,
        automatic_extractor: bool | None = None,
    ) -> DownloadResultCVM:
        """Asynchronously download documents in the current event loop."""
        if automatic_extractor is None:
            automatic_extractor = self.automatic_extractor

        result, total_files = DownloadResultCVM(), len(tasks)

        if total_files == 0:
            logger.warning('No files to download')
            return result

        logger.info(
            'Starting async download of %d files with %d concurrent downloads',
            total_files,
            self.max_concurrent,
        )

        await self._run_downloads(
            tasks, result, automatic_extractor=automatic_extractor
        )

        logger.info(
            'Download completed: %d successful, %d errors',
            result.success_count_downloads,
            result.error_count_downloads,
        )

        return result

    async def _run_downloads(
        self,
        tasks: list[DownloadTaskCVM],
        result: DownloadResultCVM,
        *,
        automatic_extractor: bool = False,
    ) -> None:
        """Execute async downloads with concurrency control."""
        progress_bar = SimpleProgressBar(
            total=len(tasks), desc='Downloading (async)'
        )
        semaphore = asyncio.Semaphore(self.max_concurrent)
        finalization_lock = asyncio.Lock()
        executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix='cvm-finalizer',
        )

        async def download_with_semaphore(task: DownloadTaskCVM) -> None:
            async with semaphore:
                url, doc_name, year, dest_path = task
                await self._download_and_extract(
                    url,
                    dest_path,
                    doc_name,
                    year,
                    result,
                    progress_bar,
                    automatic_extractor=automatic_extractor,
                    executor=executor,
                    finalization_lock=finalization_lock,
                )

        download_tasks = [
            asyncio.create_task(download_with_semaphore(task))
            for task in tasks
        ]
        try:
            await asyncio.gather(*download_tasks)
        except BaseException:
            for task in download_tasks:
                task.cancel()
            await asyncio.gather(*download_tasks, return_exceptions=True)
            raise
        finally:
            progress_bar.close()
            executor.shutdown(wait=True, cancel_futures=True)

    async def _download_and_extract(
        self,
        url: str,
        dest_path: str,
        doc_name: str,
        year: str,
        result: DownloadResultCVM,
        progress_bar: SimpleProgressBar,
        *,
        automatic_extractor: bool = False,
        executor: Executor | None = None,
        finalization_lock: asyncio.Lock | None = None,
    ) -> None:
        """Download a file and extract its contents."""
        filepath = str(
            build_download_target_path(
                url,
                dest_path,
                allowed_unc_roots=self.allowed_unc_roots,
            )
        )

        try:
            await self._process_downloaded_file(
                url,
                filepath,
                dest_path,
                doc_name,
                year,
                result,
                automatic_extractor=automatic_extractor,
                executor=executor,
                finalization_lock=finalization_lock,
            )
        finally:
            progress_bar.update(1)

    async def _process_downloaded_file(
        self,
        url: str,
        filepath: str,
        dest_path: str,
        doc_name: str,
        year: str,
        result: DownloadResultCVM,
        *,
        automatic_extractor: bool = False,
        executor: Executor | None = None,
        finalization_lock: asyncio.Lock | None = None,
    ) -> None:
        success, staged_path_or_error = await self._download_with_retry(
            url, filepath, doc_name, year
        )
        document_key = f'{doc_name}_{year}'

        if not success:
            result.add_error_downloads(
                document_key,
                staged_path_or_error or 'Unknown download error',
            )
            return
        staging_path = Path(staged_path_or_error or filepath)
        owns_staging = (
            staged_path_or_error is not None and staging_path != Path(filepath)
        )
        worker_executor = executor
        owns_executor = worker_executor is None

        try:
            expected_size = await self._get_content_length(url)
            if worker_executor is None:
                worker_executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix='cvm-finalizer',
                )
            if finalization_lock is None:
                finalization_lock = asyncio.Lock()
            if automatic_extractor:
                self.file_extractor_repository = resolve_parquet_extractor(
                    self.file_extractor_repository,
                    archive_limits=self.archive_limits,
                    allowed_unc_roots=self.allowed_unc_roots,
                )
            file_extractor_repository = (
                self.file_extractor_repository if automatic_extractor else None
            )
            finalization_result = await run_download_finalizer(
                worker_executor,
                finalization_lock,
                partial(
                    finalize_downloaded_file,
                    staging_path,
                    Path(filepath),
                    dest_path,
                    doc_name,
                    year,
                    expected_size,
                    automatic_extractor=automatic_extractor,
                    file_extractor_repository=file_extractor_repository,
                    validate_file=self._validate_downloaded_file,
                    cleanup_file=partial(remove_file, log_on_error=True),
                ),
            )
        except BaseException:
            if owns_staging:
                remove_file(str(staging_path), log_on_error=True)
            raise
        finally:
            if owns_executor and worker_executor is not None:
                worker_executor.shutdown(wait=True, cancel_futures=True)

        if finalization_result.succeeded:
            result.add_success_downloads(document_key)
            return
        result.add_error_downloads(
            document_key,
            finalization_result.error_message or 'Unknown finalization error',
        )

    async def _download_with_retry(
        self,
        url: str,
        filepath: str,
        doc_name: str,
        year: str,
    ) -> tuple[bool, str | None]:
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff = self.retry_strategy.calculate_backoff(
                        attempt - 1
                    )
                    logger.info(
                        'Retry %d/%d for %s_%s after %.1fs',
                        attempt,
                        self.max_retries,
                        doc_name,
                        year,
                        backoff,
                    )
                    await asyncio.sleep(backoff)

                staging_path = await self._stream_download(url, filepath)
                return True, (
                    str(staging_path) if staging_path is not None else None
                )
            except Exception as e:
                key = f'{doc_name}_{year}'
                if isinstance(e, _TIMEOUT_ERRORS):
                    e = DownloadTimeoutError(
                        key, self.requests_adapter.timeout
                    )
                elif isinstance(e, _NETWORK_ERRORS):
                    e = NetworkError(key, f'{type(e).__name__}: {e}')

                last_exception = e

                retryable = self.retry_strategy.is_retryable(e)
                if not retryable or attempt >= self.max_retries:
                    logger.error(
                        'Download failed for %s: %s: %s',
                        key,
                        type(e).__name__,
                        e,
                        exc_info=True,
                    )
                    break

                logger.warning(
                    'Download error for %s (attempt %d/%d): %s',
                    key,
                    attempt + 1,
                    self.max_retries + 1,
                    e,
                )

        error_msg = (
            f'{type(last_exception).__name__}: {last_exception}'
            if last_exception
            else 'Unknown error'
        )
        return False, error_msg

    async def _stream_download(self, url: str, filepath: str) -> Path:
        return await self.requests_adapter.async_download_to_staging_file(
            url=url,
            output_path=filepath,
            chunk_size=self.chunk_size,
            max_bytes=self.archive_limits.max_archive_bytes,
        )

    async def _get_content_length(self, url: str) -> int | None:
        try:
            response = await self.requests_adapter.async_head(url)
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

    def _validate_downloaded_file(
        self, filepath: str, expected_size: int | None = None
    ) -> bool:
        return validate_downloaded_file(
            filepath, expected_size, limits=self.archive_limits
        )
