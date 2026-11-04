"""Data models for B3 historical quotes extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class DocsToExtractorB3:
    """Validated inputs and resolved files for a B3 extraction run."""

    path_of_docs: str
    set_assets: set[str]
    range_years: range
    destination_path: str
    documents_to_download: set[str] = field(default_factory=set)
    all_markets: bool = False
    target_tpmerc_codes: set[str] = field(default_factory=set)
    requested_years: tuple[int, ...] = ()
    missing_years: tuple[int, ...] = ()
    validated_sources: tuple[ValidatedCotahistSource, ...] = ()
    ignored_duplicate_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class B3SourceWarning:
    """One stable, source-scoped integrity warning."""

    code: str
    count: int
    explanation: str


@dataclass(frozen=True)
class ValidatedCotahistSource:
    """Immutable source facts established before destination creation."""

    path: Path
    year: int
    member: str
    outer_sha256: str
    content_sha256: str
    uncompressed_bytes: int
    expected_rows_sha256: str
    raw_quotes: int
    selected_quotes: int
    intentional_exclusions: int
    market_counts: tuple[tuple[str, int], ...]
    unknown_market_counts: tuple[tuple[str, int], ...]
    header_bytes: bytes
    trailer_bytes: bytes
    generation_date: date
    declared_records: int
    trailer_convention: str
    blank_lines: int
    first_trading_date: date
    last_trading_date: date
    warnings: tuple[B3SourceWarning, ...] = ()


@dataclass(frozen=True)
class CotahistCatalogResolution:
    """Resolved annual sources and explicit coverage observations."""

    sources: tuple[ValidatedCotahistSource, ...]
    missing_years: tuple[int, ...]
    ignored_duplicate_sources: tuple[str, ...] = ()
