"""Assemble public results for B3 extraction outcomes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ......macro_exceptions import ExtractionError
from ......macro_infra.transactional_publication import (
    TransactionalPublication,
)
from ...integrity_report import build_integrity_report
from ...parquet_writer.schema import B3_SCHEMA_VERSION
from ...parquet_writer.verification import B3ParquetReadback
from ..scheduler import ExtractionState
from ..types import ResolvedSources
from .publication import abort_publication


def worker_failure_result(
    publication: TransactionalPublication,
    resolved: ResolvedSources,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    asset_classes: Sequence[str],
    written_by_source: dict[str, int],
    state: ExtractionState,
) -> dict[str, Any]:
    """Assemble a result describing worker failures."""
    abort_publication(publication, state.errors)
    report = build_integrity_report(
        status='failed',
        requested_years=resolved.requested_years,
        selected_sources=resolved.sources,
        missing_years=(),
        complete_market_selection=all_markets,
        market_codes=sorted(target_tpmerc_codes),
        asset_classes=asset_classes,
        ignored_duplicate_sources=resolved.ignored_duplicate_sources,
        written_by_source=written_by_source,
    )
    return summary(
        len(resolved.sources),
        0,
        len(state.errors),
        state.errors,
        None,
        integrity=report,
    )


def transaction_failure_result(
    publication: TransactionalPublication | None,
    error: Exception,
    resolved: ResolvedSources,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    asset_classes: Sequence[str],
    written_by_source: dict[str, int],
    verified_by_source: dict[str, int],
    verified_digests: dict[str, str],
    readback: B3ParquetReadback | None,
) -> dict[str, Any]:
    """Assemble a result describing transaction failure and rollback."""
    cleanup_detail = ''
    if publication is not None:
        try:
            publication.abort()
        except (ExtractionError, OSError) as cleanup_error:
            cleanup_detail = (
                '; transaction cleanup failed: '
                f'{type(cleanup_error).__name__}: {cleanup_error}'
            )
    report = build_integrity_report(
        status='failed',
        requested_years=resolved.requested_years,
        selected_sources=resolved.sources,
        missing_years=(),
        complete_market_selection=all_markets,
        market_codes=sorted(target_tpmerc_codes),
        asset_classes=asset_classes,
        ignored_duplicate_sources=resolved.ignored_duplicate_sources,
        written_by_source=written_by_source,
        verified_by_source=verified_by_source,
        verified_digests=verified_digests,
        readback=readback,
    )
    return summary(
        len(resolved.sources),
        0,
        1,
        {'transaction': (f'{type(error).__name__}: {error}{cleanup_detail}')},
        None,
        integrity=report,
    )


def summary(
    total_files: int,
    success_count: int,
    error_count: int,
    errors: dict[str, str],
    output_path: Path | None,
    total_records: int = 0,
    *,
    integrity: dict[str, Any],
) -> dict[str, Any]:
    """Build stable aggregate result counters and versioned evidence."""
    return {
        'total_files': total_files,
        'success_count': success_count,
        'error_count': error_count,
        'total_records': total_records,
        'errors': errors,
        'output_file': str(output_path) if output_path is not None else '',
        'schema_version': B3_SCHEMA_VERSION,
        'integrity': integrity,
    }
