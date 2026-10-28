"""Worker scheduling and concurrency coordination for B3 extraction."""

from __future__ import annotations

import asyncio
from concurrent.futures import (
    Executor,
    Future,
)
from pathlib import Path
from typing import Any, Protocol

from .....core import SimpleProgressBar, get_logger
from ..async_execution import run_blocking_phase
from ..executors import create_b3_executor
from ..models import ValidatedCotahistSource
from ..processing import ProcessingModeEnumB3
from ..zip_reader import ZipFileReaderB3
from .process_worker import init_worker, process_source_worker
from .resource_policy import ResourcePolicyB3
from .retry import retry_unpublished_io
from .types import SourceExtractionResult
from .zip_processor import ProcessingCancelled, ZipProcessorB3

logger = get_logger(__name__)


def _observe_source_result(
    future: asyncio.Future[SourceExtractionResult],
) -> None:
    """Retrieve failures even when cancellation leaves them for shutdown."""
    if not future.cancelled():
        future.exception()


class _ShutdownExecutor(Protocol):
    """Describe the executor surface needed during asynchronous shutdown."""

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        """Wait for submitted tasks and optionally cancel pending futures."""
        ...


class ExtractionState:
    """Accumulates completed source results and diagnostic error mappings."""

    def __init__(self) -> None:
        """Initialize empty containers for index-ordered results and errors."""
        self.results: dict[int, SourceExtractionResult] = {}
        self.errors: dict[str, str] = {}
        self.effective_backend: str = 'thread'
        self.effective_worker_limit: int = 1


class ExtractionSchedulerB3:
    """Schedules extraction tasks across threads or spawned child processes."""

    def __init__(
        self,
        zip_processor: ZipProcessorB3,
        zip_reader: ZipFileReaderB3,
        resource_policy: ResourcePolicyB3,
        *,
        processing_mode: ProcessingModeEnumB3,
        executor_backend: str = 'thread',
    ) -> None:
        """Initialize scheduler with collaborators and execution policy."""
        self.zip_processor = zip_processor
        self.zip_reader = zip_reader
        self.resource_policy = resource_policy
        self.processing_mode = processing_mode
        self.executor_backend = executor_backend

    def _create_executor(
        self,
        source_count: int,
        worker_limit: int,
    ) -> tuple[Executor, Any | None, bool]:
        """Instantiate configured thread or process worker executor."""
        return create_b3_executor(
            source_count,
            worker_limit,
            processing_mode=self.processing_mode,
            executor_backend=self.executor_backend,
            initializer=init_worker,
        )

    def _submit_source(
        self,
        executor: Executor,
        source: str,
        target_tpmerc_codes: set[str],
        temp_output: Path,
        *,
        use_processes: bool,
        cancel_event: Any | None,
        source_descriptor: ValidatedCotahistSource | None,
        all_markets: bool,
        schema_metadata: dict[bytes, bytes] | None,
    ) -> Future[SourceExtractionResult]:
        """Submit one source extraction task to the active executor."""
        if use_processes:
            return executor.submit(
                process_source_worker,
                source,
                target_tpmerc_codes,
                str(temp_output),
                python_record_limit=self.zip_processor.python_record_limit,
                archive_safety_limits=self.zip_reader.limits,
                source_descriptor=source_descriptor,
                all_markets=all_markets,
                schema_metadata=schema_metadata,
            )
        return executor.submit(
            self._process_source_with_retry,
            source,
            target_tpmerc_codes,
            temp_output,
            source_descriptor,
            all_markets,
            schema_metadata,
            cancel_event,
        )

    def _drain_completed_tasks(
        self,
        active: dict[asyncio.Future[SourceExtractionResult], tuple[int, str]],
        state: ExtractionState,
        progress_bar: SimpleProgressBar,
    ) -> bool:
        """Process finished tasks and record output results or errors.

        Returns:
            True if an error occurred and further admission should stop.
        """
        completed = [task for task in active if task.done()]
        if not completed:
            return False
        admission_stopped = False
        for task in completed:
            index, source = active.pop(task)
            try:
                state.results[index] = task.result()
                self.resource_policy.collect_after_critical_flush()
            except ProcessingCancelled:
                raise
            except Exception as error:
                logger.exception('B3 source failed: %s', source)
                state.errors[Path(source).name] = (
                    f'{type(error).__name__}: {error}'
                )
                admission_stopped = True
            progress_bar.update()
        return admission_stopped

    @staticmethod
    async def _shutdown_executor(
        executor: _ShutdownExecutor,
        cancel_event: Any | None,
        *,
        cancel_futures: bool,
    ) -> None:
        """Join workers without blocking the calling event loop."""
        if cancel_event is not None:
            cancel_event.set()
        await run_blocking_phase(
            executor.shutdown,
            wait=True,
            cancel_futures=cancel_futures,
        )

    def _process_source_with_retry(
        self,
        source: str,
        target_tpmerc_codes: set[str],
        temp_output: Path,
        source_descriptor: ValidatedCotahistSource | None,
        all_markets: bool,
        schema_metadata: dict[bytes, bytes] | None,
        cancel_event: Any | None,
    ) -> SourceExtractionResult:
        """Retry only a transient unpublished source worker operation."""
        processor = ZipProcessorB3(
            self.zip_processor.zip_reader,
            self.zip_processor.parser_factory,
            python_record_limit=self.zip_processor.python_record_limit,
            cancel_event=cancel_event,
        )
        return retry_unpublished_io(
            lambda: processor.process(
                source,
                target_tpmerc_codes,
                temp_output,
                source_descriptor=source_descriptor,
                all_markets=all_markets,
                schema_metadata=schema_metadata,
            )
        )

    async def run_sources(
        self,
        sources: list[str],
        target_tpmerc_codes: set[str],
        staging_dir: Path,
        *,
        source_descriptors: dict[str, ValidatedCotahistSource] | None = None,
        all_markets: bool = False,
        schema_metadata: dict[bytes, bytes] | None = None,
    ) -> ExtractionState:
        """Schedule at most the current worker limit without eager tasks."""
        state = ExtractionState()
        worker_limit = self.resource_policy.worker_limit(len(sources))
        active: dict[
            asyncio.Future[SourceExtractionResult], tuple[int, str]
        ] = {}
        next_index = 0
        admission_stopped = False
        shutdown_complete = False

        with SimpleProgressBar(
            total=len(sources),
            desc='Processing B3 files',
            operation='processing',
        ) as progress_bar:
            executor, cancel_event, use_processes = self._create_executor(
                len(sources), worker_limit
            )
            state.effective_backend = 'process' if use_processes else 'thread'
            state.effective_worker_limit = worker_limit

            try:
                while active or next_index < len(sources):
                    while (
                        not admission_stopped
                        and next_index < len(sources)
                        and len(active) < worker_limit
                    ):
                        if not await self.resource_policy.await_admission():
                            state.errors['resources'] = (
                                'B3 extraction stopped because resources did '
                                'not recover'
                            )
                            admission_stopped = True
                            break
                        source = sources[next_index]
                        temp_output = (
                            staging_dir
                            / 'sources'
                            / f'{next_index:05d}.parquet'
                        )
                        submitted = self._submit_source(
                            executor,
                            source,
                            target_tpmerc_codes,
                            temp_output,
                            use_processes=use_processes,
                            cancel_event=cancel_event,
                            source_descriptor=(
                                source_descriptors.get(source)
                                if source_descriptors is not None
                                else None
                            ),
                            all_markets=all_markets,
                            schema_metadata=schema_metadata,
                        )
                        future = asyncio.wrap_future(submitted)
                        future.add_done_callback(_observe_source_result)
                        active[future] = (next_index, source)
                        next_index += 1

                    if not active:
                        break

                    await asyncio.wait(
                        active, return_when=asyncio.FIRST_COMPLETED
                    )

                    if self._drain_completed_tasks(
                        active, state, progress_bar
                    ):
                        admission_stopped = True
            except (asyncio.CancelledError, ProcessingCancelled):
                await self._shutdown_executor(
                    executor,
                    cancel_event,
                    cancel_futures=True,
                )
                shutdown_complete = True
                raise
            finally:
                if not shutdown_complete:
                    await self._shutdown_executor(
                        executor,
                        None,
                        cancel_futures=False,
                    )

        return state
