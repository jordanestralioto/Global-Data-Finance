"""Transactional, bounded orchestration for B3 COTAHIST extraction."""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....core import get_logger
from .....core.config import PathSafetySettings
from .....macro_exceptions import ExtractionError
from .....macro_infra.transactional_publication import TransactionalPublisher
from ..cotahist_parser import CotahistParserB3
from ..parquet_writer.schema import build_b3_schema, schema_fingerprint
from ..processing import ProcessingModeEnumB3
from ..zip_reader import ZipFileReaderB3
from .resource_policy import ResourcePolicyB3
from .retry import retry_unpublished_io
from .temp_parquet_merge import (
    merge_temp_files_streaming,
    validate_one_temp_file,
)
from .types import SourceExtractionResult
from .zip_processor import ZipProcessorB3

if TYPE_CHECKING:
    from pyarrow import Schema

logger = get_logger(__name__)


@dataclass
class _ExtractionState:
    """Keep private source results until they can all be committed."""

    results: dict[int, SourceExtractionResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class ExtractionServiceB3:
    """Extract ordered COTAHIST sources with a bounded worker scheduler."""

    def __init__(
        self,
        zip_reader: ZipFileReaderB3,
        parser: CotahistParserB3,
        processing_mode: ProcessingModeEnumB3,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> None:
        """Store stable collaborators and source-local worker factories."""
        self.zip_reader = zip_reader
        self.parser = parser
        self.processing_mode = processing_mode
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

    @staticmethod
    def _source_sort_key(source: str) -> tuple[str, str]:
        """Preserve a deterministic merge order independent of completion."""
        path = Path(source)
        digits = ''.join(
            character for character in path.stem if character.isdigit()
        )
        return path.name.casefold(), digits

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
            state = await self._run_sources(
                sources,
                target_tpmerc_codes,
                publication.staging_dir,
            )
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
            merged_staged, merged_rows = self._prepare_staged_output(
                ordered_results,
                publication.stage_path(output_path.name),
                expected_schema,
            )
            if merged_rows != expected_rows:
                raise RuntimeError(
                    'B3 merge row-count invariant was violated: '
                    f'{merged_rows} != {expected_rows}'
                )
            publication.add_artifact(
                final_path=output_path,
                staged_path=merged_staged,
                expected_rows=merged_rows,
                schema_fingerprint=expected_fingerprint,
            )
            publication.mark_validated()
            publication.commit()
            return self._summary(
                len(sources), len(sources), 0, {}, output_path, merged_rows
            )
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
    ) -> _ExtractionState:
        """Schedule at most the current worker limit without eager tasks."""
        state = _ExtractionState()
        worker_limit = self.resource_policy.worker_limit(len(sources))
        active: dict[Future[SourceExtractionResult], tuple[int, str]] = {}
        next_index = 0
        admission_stopped = False

        with ThreadPoolExecutor(max_workers=worker_limit) as executor:
            while active or next_index < len(sources):
                while (
                    not admission_stopped
                    and next_index < len(sources)
                    and len(active) < worker_limit
                ):
                    if not await self.resource_policy.await_admission():
                        state.errors['resources'] = (
                            'B3 extraction stopped because resources did not '
                            'recover'
                        )
                        admission_stopped = True
                        break
                    source = sources[next_index]
                    temp_output = (
                        staging_dir / 'sources' / f'{next_index:05d}.parquet'
                    )
                    future = executor.submit(
                        self._process_source_with_retry,
                        source,
                        target_tpmerc_codes,
                        temp_output,
                    )
                    active[future] = (next_index, source)
                    next_index += 1

                if not active:
                    break

                completed = [task for task in active if task.done()]
                if not completed:
                    await asyncio.sleep(0.01)
                    continue
                for task in completed:
                    index, source = active.pop(task)
                    try:
                        state.results[index] = task.result()
                        self.resource_policy.collect_after_critical_flush()
                    except Exception as error:
                        logger.exception('B3 source failed: %s', source)
                        state.errors[Path(source).name] = (
                            f'{type(error).__name__}: {error}'
                        )
                        admission_stopped = True

        return state

    def _process_source_with_retry(
        self,
        source: str,
        target_tpmerc_codes: set[str],
        temp_output: Path,
    ) -> SourceExtractionResult:
        """Retry only a transient unpublished source worker operation."""
        return retry_unpublished_io(
            lambda: self.zip_processor.process(
                source, target_tpmerc_codes, temp_output
            )
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
    ) -> tuple[Path, int]:
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
            return temp_path, rows

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
        return merge_output, rows

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
