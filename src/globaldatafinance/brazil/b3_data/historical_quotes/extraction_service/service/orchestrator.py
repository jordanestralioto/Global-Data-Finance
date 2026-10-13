"""Coordinate source resolution, extraction, and publication."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from ......core import get_logger
from ......core.config import PathSafetySettings
from ......macro_exceptions import ExtractionError
from ......macro_infra.transactional_publication import (
    TransactionalPublication,
    TransactionalPublisher,
)
from ......macro_infra.transactional_publication.paths import (
    validate_artifact_destination,
)
from ...async_execution import (
    run_atomic_phase,
    run_blocking_phase,
    run_publication_phase,
)
from ...cotahist_parser import CotahistParserB3
from ...integrity_report import build_integrity_report
from ...models import ValidatedCotahistSource
from ...parquet_writer.audit_metadata import build_b3_audit_metadata
from ...parquet_writer.schema import (
    build_b3_schema,
    schema_fingerprint,
)
from ...parquet_writer.verification import B3ParquetReadback
from ...processing import ProcessingModeEnumB3
from ...zip_reader import ZipFileReaderB3
from ..resource_policy import ResourcePolicyB3
from ..scheduler import ExtractionState
from ..types import ResolvedSources
from ..zip_processor import ZipProcessorB3
from .execution import run_sources, validate_source_results
from .publication import (
    abort_after_cancellation,
    begin_publication_async,
    mark_validated_and_commit,
    merge_and_verify_output,
    verify_private_sources,
    verify_source_files,
)
from .result_assembly import (
    summary,
    transaction_failure_result,
    worker_failure_result,
)
from .source_resolution import (
    coverage_failure,
    resolve_requested_sources,
    source_sort_key,
)

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

    async def extract_from_zip_files(
        self,
        zip_files: Collection[str],
        target_tpmerc_codes: set[str],
        output_path: Path,
        *,
        validated_sources: Sequence[ValidatedCotahistSource] | None = None,
        all_markets: bool = False,
        requested_years: Sequence[int] | None = None,
        missing_years: Sequence[int] = (),
        asset_classes: Sequence[str] = (),
        ignored_duplicate_sources: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Publish only after preflight, source digests, and readback pass."""
        self.last_phase_timings = {}
        input_paths = sorted(set(zip_files), key=source_sort_key)
        resolved = await run_blocking_phase(
            resolve_requested_sources,
            input_paths,
            target_tpmerc_codes,
            validated_sources=validated_sources,
            all_markets=all_markets,
            requested_years=requested_years,
            missing_years=missing_years,
            asset_classes=asset_classes,
            ignored_duplicate_sources=ignored_duplicate_sources,
            zip_reader=self.zip_reader,
        )
        if isinstance(resolved, dict):
            return resolved
        coverage_result = coverage_failure(
            resolved,
            target_tpmerc_codes,
            all_markets,
            asset_classes,
        )
        if coverage_result is not None:
            return coverage_result
        return await self._extract_validated_sources(
            resolved,
            target_tpmerc_codes,
            output_path,
            all_markets,
            asset_classes,
        )

    async def _extract_validated_sources(
        self,
        resolved: ResolvedSources,
        target_tpmerc_codes: set[str],
        output_path: Path,
        all_markets: bool,
        asset_classes: Sequence[str],
    ) -> dict[str, Any]:
        """Run workers, verify their staged files, and publish the result."""
        sources = resolved.sources
        publisher = TransactionalPublisher(
            output_path.parent,
            owner='b3',
            source_path=str(output_path),
            allowed_unc_roots=self.allowed_unc_roots,
        )
        publication: TransactionalPublication | None = None
        written_by_source: dict[str, int] = {}
        verified_by_source: dict[str, int] = {}
        verified_digests: dict[str, str] = {}
        readback: B3ParquetReadback | None = None
        try:
            final = validate_artifact_destination(
                output_path, publisher.destination_dir
            )
            if any(final == source.path.resolve() for source in sources):
                raise ExtractionError(
                    str(final),
                    'B3 output path cannot replace a COTAHIST source',
                )
            expected_fingerprint = schema_fingerprint(build_b3_schema())
            schema_metadata = build_b3_audit_metadata(
                sources,
                schema_fingerprint=expected_fingerprint,
                requested_years=resolved.requested_years,
                asset_classes=asset_classes,
                target_tpmerc_codes=target_tpmerc_codes,
                all_markets=all_markets,
            )
            expected_schema = build_b3_schema(schema_metadata)
            publication = await begin_publication_async(publisher, sources)
            source_started = time.perf_counter()
            source_paths = [str(source.path) for source in sources]
            descriptors = {str(source.path): source for source in sources}
            state = await self._run_sources(
                source_paths,
                target_tpmerc_codes,
                publication.staging_dir,
                source_descriptors=descriptors,
                all_markets=all_markets,
                schema_metadata=schema_metadata,
            )
            source_wall = time.perf_counter() - source_started
            source_results = [
                state.results[index]
                for index in range(len(source_paths))
                if index in state.results
            ]
            written_by_source = {
                result.source_path.name: result.written_records
                for result in source_results
            }
            if state.errors:
                return await run_blocking_phase(
                    worker_failure_result,
                    publication,
                    resolved,
                    target_tpmerc_codes,
                    all_markets,
                    asset_classes,
                    written_by_source,
                    state,
                )

            ordered_results = [
                state.results[index] for index in range(len(source_paths))
            ]
            validate_source_results(
                ordered_results, expected_fingerprint, sources
            )
            await run_blocking_phase(
                verify_private_sources,
                ordered_results,
                expected_schema,
                sources,
            )
            merged_result = await run_blocking_phase(
                merge_and_verify_output,
                ordered_results,
                publication,
                output_path,
                expected_schema,
            )
            (
                merged_staged,
                readback,
                verified_by_source,
                verified_digests,
                staged_sha256,
                merge_wall,
                validation_wall,
                merge_bypassed,
            ) = merged_result
            publication.add_artifact(
                final_path=output_path,
                staged_path=merged_staged,
                expected_rows=readback.row_count,
                schema_fingerprint=expected_fingerprint,
            )
            report = build_integrity_report(
                status='passed',
                requested_years=resolved.requested_years,
                selected_sources=sources,
                missing_years=(),
                complete_market_selection=all_markets,
                market_codes=sorted(target_tpmerc_codes),
                asset_classes=asset_classes,
                ignored_duplicate_sources=resolved.ignored_duplicate_sources,
                written_by_source=written_by_source,
                verified_by_source=verified_by_source,
                verified_digests=verified_digests,
                readback=readback,
                output_sha256=staged_sha256,
            )
            await asyncio.sleep(0)
            cleanup_warning = await run_publication_phase(
                partial(verify_source_files, sources),
                partial(mark_validated_and_commit, publication),
            )
            if cleanup_warning is not None:
                report['warnings'].append(cleanup_warning)
            self.last_phase_timings = {
                'source_wall_seconds': source_wall,
                'merge_wall_seconds': None if merge_bypassed else merge_wall,
                'merge_status': 'bypassed' if merge_bypassed else 'completed',
                'validation_wall_seconds': validation_wall,
                'effective_backend': state.effective_backend,
                'effective_worker_limit': state.effective_worker_limit,
            }
            return summary(
                len(sources),
                len(sources),
                0,
                {},
                output_path,
                readback.row_count,
                integrity=report,
            )
        except asyncio.CancelledError:
            await run_atomic_phase(abort_after_cancellation, publication)
            raise
        except Exception as error:
            logger.exception('B3 extraction transaction failed')
            return await run_blocking_phase(
                transaction_failure_result,
                publication,
                error,
                resolved,
                target_tpmerc_codes,
                all_markets,
                asset_classes,
                written_by_source,
                verified_by_source,
                verified_digests,
                readback,
            )

    async def _run_sources(
        self,
        sources: list[str],
        target_tpmerc_codes: set[str],
        staging_dir: Path,
        *,
        source_descriptors: dict[str, ValidatedCotahistSource],
        all_markets: bool,
        schema_metadata: dict[bytes, bytes],
    ) -> ExtractionState:
        """Delegate source execution while retaining the scheduler seam."""
        return await run_sources(
            self.zip_processor,
            self.zip_reader,
            self.resource_policy,
            self.processing_mode,
            self.executor_backend,
            sources,
            target_tpmerc_codes,
            staging_dir,
            source_descriptors=source_descriptors,
            all_markets=all_markets,
            schema_metadata=schema_metadata,
        )
