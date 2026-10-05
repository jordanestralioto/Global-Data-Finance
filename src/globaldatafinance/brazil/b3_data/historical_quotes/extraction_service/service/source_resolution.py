"""Resolve and validate the requested COTAHIST source set."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ......macro_exceptions import ExtractionError
from ...catalog import resolve_cotahist_sources
from ...errors import CotahistCatalogError
from ...integrity_report import build_integrity_report
from ...models import CotahistCatalogResolution, ValidatedCotahistSource
from ...zip_reader import ZipFileReaderB3
from ..types import ResolvedSources
from .result_assembly import summary

_SOURCE_YEAR_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})\.(?:ZIP|TXT)$', re.IGNORECASE
)


def catalog_error_key(error: CotahistCatalogError | ExtractionError) -> str:
    """Choose the source basename when catalog validation retained one."""
    if isinstance(error, CotahistCatalogError) and error.source_path:
        return error.source_path.name
    return 'catalog'


def source_sort_key(source: str) -> tuple[int, str, str]:
    """Order source files by annual year and deterministic basename."""
    path = Path(source)
    match = _SOURCE_YEAR_PATTERN.fullmatch(path.name)
    year = int(match.group('year')) if match is not None else 9999
    return year, path.name.casefold(), path.name


def resolve_requested_sources(
    input_paths: list[str],
    target_tpmerc_codes: set[str],
    *,
    validated_sources: Sequence[ValidatedCotahistSource] | None,
    all_markets: bool,
    requested_years: Sequence[int] | None,
    missing_years: Sequence[int],
    asset_classes: Sequence[str],
    ignored_duplicate_sources: Sequence[str],
    zip_reader: ZipFileReaderB3,
) -> ResolvedSources | dict[str, Any]:
    """Resolve inputs and report catalog failures through the result."""
    try:
        if validated_sources is None:
            resolution = preflight_input_paths(
                input_paths,
                target_tpmerc_codes,
                all_markets,
                requested_years,
                zip_reader=zip_reader,
            )
            sources = resolution.sources
            resolved_missing = resolution.missing_years
            ignored_sources = resolution.ignored_duplicate_sources
        else:
            sources = tuple(
                sorted(
                    validated_sources,
                    key=lambda source: (
                        source.year,
                        source.path.name.casefold(),
                        source.path.name,
                    ),
                )
            )
            resolved_missing = tuple(sorted(set(missing_years)))
            ignored_sources = tuple(ignored_duplicate_sources)
    except (CotahistCatalogError, ExtractionError) as error:
        error_key = catalog_error_key(error)
        report = build_integrity_report(
            status='failed',
            requested_years=requested_years or (),
            selected_sources=(),
            missing_years=missing_years,
            complete_market_selection=all_markets,
            market_codes=sorted(target_tpmerc_codes),
            asset_classes=asset_classes,
            ignored_duplicate_sources=ignored_duplicate_sources,
        )
        return summary(
            len(input_paths),
            0,
            1,
            {error_key: f'{type(error).__name__}: {error}'},
            None,
            integrity=report,
        )
    resolved_years = tuple(
        requested_years
        if requested_years is not None
        else (source.year for source in sources)
    )
    return ResolvedSources(
        tuple(sources),
        resolved_years,
        tuple(resolved_missing),
        tuple(ignored_sources),
    )


def coverage_failure(
    resolved: ResolvedSources,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    asset_classes: Sequence[str],
) -> dict[str, Any] | None:
    """Build a result describing incomplete source coverage."""
    if resolved.missing_years:
        report = build_integrity_report(
            status='failed',
            requested_years=resolved.requested_years,
            selected_sources=resolved.sources,
            missing_years=resolved.missing_years,
            complete_market_selection=all_markets,
            market_codes=sorted(target_tpmerc_codes),
            asset_classes=asset_classes,
            ignored_duplicate_sources=resolved.ignored_duplicate_sources,
        )
        return summary(
            len(resolved.sources),
            0,
            1,
            {
                'coverage': (
                    'Missing requested COTAHIST years: '
                    f'{list(resolved.missing_years)}'
                )
            },
            None,
            integrity=report,
        )
    if resolved.sources:
        return None
    report = build_integrity_report(
        status='failed',
        requested_years=resolved.requested_years,
        selected_sources=(),
        missing_years=(),
        complete_market_selection=all_markets,
        market_codes=sorted(target_tpmerc_codes),
        asset_classes=asset_classes,
        ignored_duplicate_sources=resolved.ignored_duplicate_sources,
    )
    return summary(
        0,
        0,
        1,
        {'catalog': 'No matching COTAHIST input files were found'},
        None,
        integrity=report,
    )


def preflight_input_paths(
    paths: list[str],
    target_tpmerc_codes: set[str],
    all_markets: bool,
    requested_years: Sequence[int] | None,
    *,
    zip_reader: ZipFileReaderB3,
) -> CotahistCatalogResolution:
    """Resolve direct service inputs through the production catalog."""
    if not paths:
        return CotahistCatalogResolution((), tuple(requested_years or ()))
    parents = {Path(path).resolve().parent for path in paths}
    if len(parents) != 1:
        raise CotahistCatalogError(
            'B3 extraction inputs must belong to one caller-owned catalog'
        )
    inferred_years = tuple(
        sorted({year_from_path(Path(path)) for path in paths})
    )
    expected_years = tuple(requested_years or inferred_years)
    return resolve_cotahist_sources(
        next(iter(parents)),
        expected_years=expected_years,
        target_tpmerc_codes=target_tpmerc_codes,
        all_markets=all_markets,
        limits=zip_reader.limits,
    )


def year_from_path(path: Path) -> int:
    """Resolve the annual year from the external filename contract."""
    match = _SOURCE_YEAR_PATTERN.fullmatch(path.name)
    if match is None:
        raise CotahistCatalogError(
            f'Invalid COTAHIST annual filename: {path.name}'
        )
    return int(match.group('year'))
