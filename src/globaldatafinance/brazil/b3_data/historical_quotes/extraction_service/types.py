"""Typed internal results for the bounded B3 extraction workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from ..cotahist_parser import B3ParserMetrics
from ..models import ValidatedCotahistSource

ParsedRecord = dict[str, Any]


@dataclass(frozen=True)
class ResolvedSources:
    """Validated inputs, requested coverage, and duplicate observations."""

    sources: tuple[ValidatedCotahistSource, ...]
    requested_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    ignored_duplicate_sources: tuple[str, ...]


@dataclass(frozen=True)
class SourceExtractionResult:
    """One fully parsed source and its uncommitted temporary artifact."""

    source_path: Path
    zip_member: str
    source: ValidatedCotahistSource
    temp_path: Path | None
    selected_records: int
    parsed_records: int
    written_records: int
    metrics: B3ParserMetrics
    schema_fingerprint: str
    expected_rows_sha256: str
    parsed_rows_sha256: str


class ExtractionSummary(TypedDict):
    """Aggregate result fields reported by the stable B3 use case."""

    total_files: int
    success_count: int
    error_count: int
    total_records: int
    errors: dict[str, str]
    output_file: str
