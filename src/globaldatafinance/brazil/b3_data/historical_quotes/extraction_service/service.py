"""Transactional, bounded orchestration for B3 COTAHIST extraction."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....core import get_logger
from .....core.config import PathSafetySettings
from .....macro_exceptions import ExtractionError
from .....macro_infra.transactional_publication import (
    TransactionalPublication,
    TransactionalPublisher,
)
from ..cotahist_parser import CotahistParserB3
from ..parquet_writer.schema import build_b3_schema, schema_fingerprint
from ..processing import ProcessingModeEnumB3
from ..zip_reader import ZipFileReaderB3
from .resource_policy import ResourcePolicyB3
from .retry import retry_unpublished_io
from .scheduler import ExtractionSchedulerB3, ExtractionState
from .temp_parquet_merge import (
    merge_temp_files_streaming,
    validate_one_temp_file,
)
from .types import SourceExtractionResult
from .zip_processor import ZipProcessorB3

if TYPE_CHECKING:
    from pyarrow import Schema

logger = get_logger(__name__)


class ExtractionServiceB3:
    """Extract ordered COTAHIST sources with a bounded worker scheduler."""

    def __init__(
        self,
        zip_reader: ZipFileReaderB3,
        parser: CotahistParserB3,
        processing_mode: ProcessingModeEnumB3,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
        executor_backend: str = 'thread',
    ) -> None:
        """Store stable collaborators and source-local worker factories."""
        if executor_backend not in ('thread', 'process'):
            raise ValueError(
                f'Invalid executor_backend: {executor_backend!r}. '
                "Must be 'thread' or 'process'."
            )
        self.zip_reader = zip_reader
        self.parser = parser
        self.processing_mode = processing_mode
        self.executor_backend = executor_backend
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        self.resource_policy = ResourcePolicyB3(processing_mode)
        self.zip_processor = ZipProcessorB3(
            zip_reader=zip_reader,
            parser_factory=type(parser),
            python_record_limit=(
                25_000
                if processing_mode is ProcessingModeEnumB3.FAST
                else 10_000
            ),
        )
        self.last_phase_timings: dict[str, Any] = {}

    @staticmethod
    def _source_sort_key(source: str) -> tuple[str, str]:
        """Preserve a deterministic merge order independent of completion."""
        path = Path(source)
        digits = ''.join(
            character for character in path.stem if character.isdigit()
        )
        return path.name.casefold(), digits

    @staticmethod
    def _abort_after_cancellation(
        publication: TransactionalPublication | None,
    ) -> None:
        """Abort unpublished state without replacing cancellation."""
        if publication is None:
            return
        try:
            publication.abort()
        except Exception:
            logger.exception(
                'B3 transaction cleanup failed during cancellation'
            )

    async def extract_from_zip_files(
        self,
        zip_files: Collection[str],
        target_tpmerc_codes: set[str],
        output_path: Path,
    ) -> dict[str, Any]:
        """Produce one recoverably published output or a rollback summary."""
        sources = sorted(zip_files, key=self._source_sort_key)
        if not sources:
            return self._summary(0, 0, 0, {}, None)

        publisher = TransactionalPublisher(
            output_path.parent,
            owner='b3',
            source_path=str(output_path),
            allowed_unc_roots=self.allowed_unc_roots,
        )
        publication = None
        try:
            required_bytes = sum(
                Path(source).stat().st_size
                for source in sources
                if Path(source).is_file()
            )
            publication = publisher.begin(
                source_descriptors=[
                    {'source': Path(source).name} for source in sources
                ],
                required_bytes=required_bytes,
            )
            expected_schema = build_b3_schema()
            expected_fingerprint = schema_fingerprint(expected_schema)

            source_started = time.perf_counter()
            state = await self._run_sources(
                sources,
                target_tpmerc_codes,
                publication.staging_dir,
            )
            source_wall = time.perf_counter() - source_started

            if state.errors:
                try:
                    publication.abort()
                except (ExtractionError, OSError) as cleanup_error:
                    state.errors['transaction'] = (
                        'B3 source failure was followed by incomplete '
                        'transaction cleanup: '
                        f'{type(cleanup_error).__name__}: '
                        f'{cleanup_error}'
                    )
                return self._summary(
                    len(sources), 0, len(state.errors), state.errors, None
                )

            ordered_results = [
                state.results[index] for index in range(len(sources))
            ]
            self._validate_source_results(
                ordered_results, expected_fingerprint
            )
            expected_rows = sum(
                result.written_records for result in ordered_results
            )

            merge_started = time.perf_counter()
            merged_staged, merged_rows, merge_bypassed = (
                self._prepare_staged_output(
                    ordered_results,
                    publication.stage_path(output_path.name),
                    expected_schema,
                )
            )
            merge_wall = time.perf_counter() - merge_started

            if merged_rows != expected_rows:
                raise RuntimeError(
                    'B3 merge row-count invariant was violated: '
                    f'{merged_rows} != {expected_rows}'
                )

            validation_started = time.perf_counter()
            publication.add_artifact(
                final_path=output_path,
                staged_path=merged_staged,
                expected_rows=merged_rows,
                schema_fingerprint=expected_fingerprint,
            )
            publication.mark_validated()
            publication.commit()
            validation_wall = time.perf_counter() - validation_started

            self.last_phase_timings = {
                'source_wall_seconds': source_wall,
                'merge_wall_seconds': None if merge_bypassed else merge_wall,
                'merge_status': 'bypassed' if merge_bypassed else 'completed',
                'validation_wall_seconds': validation_wall,
                'effective_backend': state.effective_backend,
                'effective_worker_limit': state.effective_worker_limit,
            }

            return self._summary(
                len(sources), len(sources), 0, {}, output_path, merged_rows
            )
        except asyncio.CancelledError:
            self._abort_after_cancellation(publication)
            raise
        except Exception as error:
            logger.exception('B3 extraction failed before publication')
            cleanup_detail = ''
            if publication is not None:
                try:
                    publication.abort()
                except (ExtractionError, OSError) as cleanup_error:
                    cleanup_detail = (
                        '; transaction cleanup failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
            return self._summary(
                len(sources),
                0,
                1,
                {
                    'transaction': (
                        f'{type(error).__name__}: {error}{cleanup_detail}'
                    )
                },
                None,
            )

    async def _run_sources(
        self,
        sources: list[str],
        target_tpmerc_codes: set[str],
        staging_dir: Path,
    ) -> ExtractionState:
        """Schedule at most the current worker limit without eager tasks."""
        scheduler = ExtractionSchedulerB3(
            zip_processor=self.zip_processor,
            zip_reader=self.zip_reader,
            resource_policy=self.resource_policy,
            processing_mode=self.processing_mode,
            executor_backend=self.executor_backend,
        )
        return await scheduler.run_sources(
            sources, target_tpmerc_codes, staging_dir
        )

    @staticmethod
    def _validate_source_results(
        results: list[SourceExtractionResult], expected_fingerprint: str
    ) -> None:
        """Prove all workers honored parser, writer, and schema invariants."""
        for result in results:
            if (
                result.selected_records != result.parsed_records
                or result.parsed_records != result.written_records
            ):
                raise RuntimeError(
                    f'B3 source invariant failed for {result.source_path.name}'
                )
            if (
                result.temp_path is not None
                and result.schema_fingerprint != expected_fingerprint
            ):
                raise RuntimeError(
                    f'B3 source schema mismatch for {result.source_path.name}'
                )

    @staticmethod
    def _prepare_staged_output(
        results: list[SourceExtractionResult],
        merge_output: Path,
        expected_schema: Schema,
    ) -> tuple[Path, int, bool]:
        """Reuse one validated source artifact or merge ordered artifacts.

        A one-source request has already produced a closed, schema-validated
        Parquet artifact in transaction staging.  Publishing that artifact
        directly preserves the same validation boundary as a merge and avoids
        a costly duplicate read/write cycle.  Empty and multi-source requests
        retain the canonical merge path.
        """
        temporary_results = [
            result for result in results if result.temp_path is not None
        ]
        if len(temporary_results) == 1 and len(results) == 1:
            source = temporary_results[0]
            temp_path = source.temp_path
            if temp_path is None:
                raise RuntimeError('B3 source temporary artifact is missing')
            rows = retry_unpublished_io(
                lambda: validate_one_temp_file(
                    temp_path,
                    expected_schema,
                    source.written_records,
                )
            )
            return temp_path, rows, True

        temp_files: list[Path] = []
        for result in temporary_results:
            if result.temp_path is None:
                raise RuntimeError('B3 source temporary artifact is missing')
            temp_files.append(result.temp_path)
        expected_rows = [
            result.written_records for result in temporary_results
        ]
        rows = retry_unpublished_io(
            lambda: merge_temp_files_streaming(
                temp_files, merge_output, expected_schema, expected_rows
            )
        )
        return merge_output, rows, False

    @staticmethod
    def _summary(
        total_files: int,
        success_count: int,
        error_count: int,
        errors: dict[str, str],
        output_path: Path | None,
        total_records: int = 0,
    ) -> dict[str, Any]:
        """Build the established public B3 aggregate shape."""
        return {
            'total_files': total_files,
            'success_count': success_count,
            'error_count': error_count,
            'total_records': total_records,
            'errors': errors,
            'output_file': str(output_path) if output_path is not None else '',
        }
