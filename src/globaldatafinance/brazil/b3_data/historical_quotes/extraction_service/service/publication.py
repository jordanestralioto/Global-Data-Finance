"""Publish and verify extracted B3 Parquet artifacts."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from ......core import get_logger
from ......macro_exceptions import ExtractionError
from ......macro_infra.transactional_publication import (
    TransactionalPublication,
    TransactionalPublisher,
)
from ...async_execution import run_atomic_phase, run_blocking_phase
from ...integrity import sha256_file
from ...models import ValidatedCotahistSource
from ...parquet_writer.verification import (
    B3ParquetReadback,
    verify_b3_parquet,
    verify_b3_parquet_metadata,
)
from ..retry import retry_unpublished_io
from ..temp_parquet_merge import merge_temp_files_streaming
from ..types import SourceExtractionResult

if TYPE_CHECKING:
    from pyarrow import Schema


logger = get_logger(__name__)


def mark_validated_and_commit(
    publication: TransactionalPublication,
) -> dict[str, object] | None:
    """Publish immediately after the final worker verification decision."""
    publication.mark_validated()
    return commit_with_cleanup_warning(publication)


def commit_with_cleanup_warning(
    publication: TransactionalPublication,
) -> dict[str, object] | None:
    """Preserve the committed outcome if only derived-state cleanup fails."""
    try:
        publication.commit()
    except ExtractionError as error:
        if publication.manifest.phase not in {'COMMITTED', 'CLEANUP_PENDING'}:
            raise
        detail = f'{type(error).__name__}: {error}'
        code = 'PUBLICATION_CLEANUP_RECOVERED'
        try:
            publication.abort()
        except Exception as cleanup_error:
            logger.exception('B3 committed cleanup retry failed')
            code = 'PUBLICATION_CLEANUP_PENDING'
            detail += (
                '; cleanup retry failed: '
                f'{type(cleanup_error).__name__}: {cleanup_error}'
            )
        logger.warning('B3 committed publication cleanup: %s', detail)
        return {
            'code': code,
            'source': publication.manifest.artifacts[0].final_path.name,
            'count': 1,
            'explanation': detail,
        }
    return None


def verify_source_files(sources: Sequence[ValidatedCotahistSource]) -> None:
    """Recheck immutable source identities immediately before publication."""
    for source in sources:
        try:
            current_sha256 = sha256_file(source.path)
        except OSError as error:
            raise ExtractionError(
                source.path.name,
                f'Cannot recheck B3 source before publication: {error}',
            ) from error
        if current_sha256 != source.outer_sha256:
            raise ExtractionError(
                source.path.name,
                'B3 source changed after validation and before publication',
            )


def abort_after_cancellation(
    publication: TransactionalPublication | None,
) -> None:
    """Abort unpublished state without replacing cancellation."""
    if publication is None:
        return
    try:
        publication.abort()
    except Exception:
        logger.exception('B3 transaction cleanup failed during cancellation')


def begin_publication(
    publisher: TransactionalPublisher,
    sources: Sequence[ValidatedCotahistSource],
) -> TransactionalPublication:
    """Start a transactional publication for the validated source set."""
    required_bytes = sum(
        (source.uncompressed_bytes * 2) + (source.selected_quotes * 256)
        for source in sources
    )
    return publisher.begin(
        source_descriptors=[
            {
                'source': source.path.name,
                'year': str(source.year),
                'outer_sha256': source.outer_sha256,
                'content_sha256': source.content_sha256,
            }
            for source in sources
        ],
        required_bytes=required_bytes,
    )


async def begin_publication_async(
    publisher: TransactionalPublisher,
    sources: Sequence[ValidatedCotahistSource],
) -> TransactionalPublication:
    """Join acquisition and retain cleanup ownership on cancellation."""
    publication: TransactionalPublication | None = None

    def acquire() -> TransactionalPublication:
        nonlocal publication
        publication = begin_publication(publisher, sources)
        return publication

    try:
        return await run_blocking_phase(acquire)
    except asyncio.CancelledError:
        await run_atomic_phase(abort_after_cancellation, publication)
        raise


def verify_private_sources(
    results: list[SourceExtractionResult],
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
) -> None:
    """Check private worker artifacts' metadata before they are merged.

    Row values, provenance, order, and digests are proven once by the full
    readback of the staged output. The merge rewrites the footer, so private
    footer evidence must be validated here, before it can be overwritten.
    """
    for result in results:
        temp_path = result.temp_path
        if temp_path is None:
            if result.written_records != 0:
                raise ExtractionError(
                    result.source_path.name,
                    'A nonempty B3 source lost its private artifact',
                )
            continue
        retry_unpublished_io(
            partial(
                verify_b3_parquet_metadata,
                temp_path,
                expected_schema=expected_schema,
                sources=(result.source,),
                manifest_sources=sources,
            )
        )


def merge_and_verify_output(
    results: list[SourceExtractionResult],
    publication: TransactionalPublication,
    output_path: Path,
    expected_schema: Schema,
) -> tuple[
    Path,
    B3ParquetReadback,
    dict[str, int],
    dict[str, str],
    str,
    float,
    float,
    bool,
]:
    """Merge private outputs and verify the published artifact."""
    expected_rows = sum(result.written_records for result in results)
    merge_started = time.perf_counter()
    merged_staged, merged_rows, merge_bypassed = prepare_staged_output(
        results,
        publication.stage_path(output_path.name),
        expected_schema,
    )
    merge_wall = time.perf_counter() - merge_started
    if merged_rows != expected_rows:
        raise ExtractionError(
            str(merged_staged),
            'B3 merge row-count invariant was violated: '
            f'{merged_rows} != {expected_rows}',
        )
    validation_started = time.perf_counter()
    readback = retry_unpublished_io(
        partial(
            verify_b3_parquet,
            merged_staged,
            expected_schema=expected_schema,
            sources=tuple(result.source for result in results),
        )
    )
    validation_wall = time.perf_counter() - validation_started
    verified_by_source = {
        result.source_path.name: rows
        for result, rows in zip(
            results, readback.source_row_counts, strict=True
        )
    }
    verified_digests = {
        result.source_path.name: digest
        for result, digest in zip(
            results, readback.source_digests, strict=True
        )
    }
    return (
        merged_staged,
        readback,
        verified_by_source,
        verified_digests,
        sha256_file(merged_staged),
        merge_wall,
        validation_wall,
        merge_bypassed,
    )


def abort_publication(
    publication: TransactionalPublication,
    errors: dict[str, str],
) -> None:
    """Abort artifacts while preserving the first source failures."""
    try:
        publication.abort()
    except (ExtractionError, OSError) as cleanup_error:
        errors['transaction'] = (
            'B3 source failure was followed by incomplete transaction '
            'cleanup: '
            f'{type(cleanup_error).__name__}: {cleanup_error}'
        )


def prepare_staged_output(
    results: list[SourceExtractionResult],
    merge_output: Path,
    expected_schema: Schema,
) -> tuple[Path, int, bool]:
    """Reuse one verified source artifact or merge ordered artifacts."""
    temporary_results = [
        result for result in results if result.temp_path is not None
    ]
    if len(temporary_results) == 1 and len(results) == 1:
        source = temporary_results[0]
        temp_path = source.temp_path
        if temp_path is None:
            raise RuntimeError('B3 source temporary artifact is missing')
        return temp_path, source.written_records, True

    temp_files: list[Path] = []
    for result in temporary_results:
        if result.temp_path is None:
            raise RuntimeError('B3 source temporary artifact is missing')
        temp_files.append(result.temp_path)
    expected_rows = [result.written_records for result in temporary_results]
    rows = retry_unpublished_io(
        lambda: merge_temp_files_streaming(
            temp_files,
            merge_output,
            expected_schema,
            expected_rows,
        )
    )
    return merge_output, rows, False
