"""Build the public B3 integrity report from verified source facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal

from .models import ValidatedCotahistSource
from .parquet_writer.verification import (
    B3ParquetReadback,
)
from .source_evidence import build_source_evidence


def build_integrity_report(
    *,
    status: Literal['passed', 'failed', 'not_run'],
    requested_years: Sequence[int],
    selected_sources: Sequence[ValidatedCotahistSource],
    missing_years: Sequence[int],
    complete_market_selection: bool,
    market_codes: Sequence[str],
    asset_classes: Sequence[str],
    ignored_duplicate_sources: Sequence[str] = (),
    written_by_source: Mapping[str, int] | None = None,
    verified_by_source: Mapping[str, int] | None = None,
    verified_digests: Mapping[str, str] | None = None,
    readback: B3ParquetReadback | None = None,
    output_sha256: str | None = None,
) -> dict[str, Any]:
    """Apply the public completeness definitions to observable evidence."""
    written_counts = dict(written_by_source or {})
    verified_counts = dict(verified_by_source or {})
    actual_digests = dict(verified_digests or {})
    raw_quotes = sum(source.raw_quotes for source in selected_sources)
    selected_quotes = sum(
        source.selected_quotes for source in selected_sources
    )
    intentional_exclusions = sum(
        source.intentional_exclusions for source in selected_sources
    )
    written_rows = sum(written_counts.values())
    verified_rows = sum(verified_counts.values())
    passed = status == 'passed'
    selection_complete = (
        passed and selected_quotes == written_rows == verified_rows
    )
    source_complete = (
        selection_complete
        and intentional_exclusions == 0
        and raw_quotes == written_rows == verified_rows
    )
    unknown_counts: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    for source in selected_sources:
        for code, count in source.unknown_market_counts:
            unknown_counts[code] = unknown_counts.get(code, 0) + count
        for warning in source.warnings:
            warnings.append(
                {
                    'code': warning.code,
                    'source': source.path.name,
                    'count': warning.count,
                    'explanation': warning.explanation,
                }
            )
        if source.raw_quotes and source.selected_quotes == 0:
            warnings.append(
                {
                    'code': 'NO_SELECTED_QUOTES',
                    'source': source.path.name,
                    'count': source.intentional_exclusions,
                    'explanation': (
                        'The source passed validation, but the requested '
                        'market selection excluded every quotation.'
                    ),
                }
            )
    for duplicate in ignored_duplicate_sources:
        warnings.append(
            {
                'code': 'IGNORED_EQUIVALENT_TXT',
                'source': Path(duplicate).name,
                'count': 1,
                'explanation': (
                    'The TXT source was fully validated and its uncompressed '
                    'bytes matched the selected ZIP source.'
                ),
            }
        )
    sources = [
        _source_report(
            source,
            written_rows=written_counts.get(source.path.name, 0),
            verified_rows=verified_counts.get(source.path.name, 0),
            verified_digest=actual_digests.get(source.path.name),
        )
        for source in selected_sources
    ]
    source_dates = [
        value
        for source in selected_sources
        for value in (source.first_trading_date, source.last_trading_date)
    ]
    method = (
        'bounded full Parquet readback against preflight source digests'
        if readback is not None
        else 'not completed'
    )
    return {
        'status': status,
        'schema_version': 2,
        'verification_method': method,
        'requested_years': list(requested_years),
        'selected_years': [source.year for source in selected_sources],
        'missing_years': list(missing_years),
        'complete_market_selection': complete_market_selection,
        'market_codes': []
        if complete_market_selection
        else sorted(market_codes),
        'asset_classes': sorted(set(asset_classes)),
        'raw_quotes': raw_quotes,
        'selected_quotes': selected_quotes,
        'intentional_exclusions': intentional_exclusions,
        'excluded_records': intentional_exclusions,
        'written_rows': written_rows,
        'verified_rows': verified_rows,
        'selection_complete': selection_complete,
        'source_complete': source_complete,
        'source_first_trading_date': _date_text(min(source_dates))
        if source_dates
        else None,
        'source_last_trading_date': _date_text(max(source_dates))
        if source_dates
        else None,
        'output_first_trading_date': _date_text(readback.first_trading_date)
        if readback is not None
        else None,
        'output_last_trading_date': _date_text(readback.last_trading_date)
        if readback is not None
        else None,
        'unknown_market_counts': dict(sorted(unknown_counts.items())),
        'warnings': warnings,
        'sources': sources,
        'ignored_duplicate_sources': list(ignored_duplicate_sources),
        'output_sha256': output_sha256,
    }


def _source_report(
    source: ValidatedCotahistSource,
    *,
    written_rows: int,
    verified_rows: int,
    verified_digest: str | None,
) -> dict[str, Any]:
    """Project source descriptor and output observations into the API."""
    return {
        **build_source_evidence(source),
        'excluded_records': source.intentional_exclusions,
        'written_rows': written_rows,
        'verified_rows': verified_rows,
        'verified_rows_sha256': verified_digest,
    }


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None
