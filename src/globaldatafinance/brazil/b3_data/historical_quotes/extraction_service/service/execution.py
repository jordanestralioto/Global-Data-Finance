"""Run source workers and collect their extraction results."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ......macro_exceptions import ExtractionError
from ...models import ValidatedCotahistSource
from ...processing import ProcessingModeEnumB3
from ...zip_reader import ZipFileReaderB3
from ..resource_policy import ResourcePolicyB3
from ..scheduler import ExtractionSchedulerB3, ExtractionState
from ..types import SourceExtractionResult
from ..zip_processor import ZipProcessorB3


async def run_sources(
    zip_processor: ZipProcessorB3,
    zip_reader: ZipFileReaderB3,
    resource_policy: ResourcePolicyB3,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
    sources: list[str],
    target_tpmerc_codes: set[str],
    staging_dir: Path,
    *,
    source_descriptors: dict[str, ValidatedCotahistSource],
    all_markets: bool,
    schema_metadata: dict[bytes, bytes],
) -> ExtractionState:
    """Schedule validated sources under the existing resource policy."""
    scheduler = ExtractionSchedulerB3(
        zip_processor=zip_processor,
        zip_reader=zip_reader,
        resource_policy=resource_policy,
        processing_mode=processing_mode,
        executor_backend=executor_backend,
    )
    return await scheduler.run_sources(
        sources,
        target_tpmerc_codes,
        staging_dir,
        source_descriptors=source_descriptors,
        all_markets=all_markets,
        schema_metadata=schema_metadata,
    )


def validate_source_results(
    results: list[SourceExtractionResult],
    expected_fingerprint: str,
    sources: Sequence[ValidatedCotahistSource],
) -> None:
    """Prove worker outputs match their immutable source descriptors."""
    if len(results) != len(sources):
        raise ExtractionError(
            'B3 extraction', 'Not every validated source returned a result'
        )
    for result, source in zip(results, sources, strict=True):
        if (
            result.source.selected_quotes != result.written_records
            or result.selected_records != result.parsed_records
            or result.parsed_records != result.written_records
        ):
            raise ExtractionError(
                result.source_path.name,
                'B3 source parser/write count invariant failed',
            )
        if result.source != source:
            raise ExtractionError(
                result.source_path.name,
                'B3 worker returned a different validated source descriptor',
            )
        if result.parsed_rows_sha256 != source.expected_rows_sha256:
            raise ExtractionError(
                result.source_path.name,
                'B3 worker row digest differs from source preflight',
            )
        if (
            result.temp_path is not None
            and result.schema_fingerprint != expected_fingerprint
        ):
            raise ExtractionError(
                result.source_path.name,
                'B3 source Parquet logical schema fingerprint mismatch',
            )
