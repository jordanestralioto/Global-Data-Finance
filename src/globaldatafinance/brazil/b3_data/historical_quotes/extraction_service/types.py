"""Typed internal results for the bounded B3 extraction workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from ..cotahist_parser import B3ParserMetrics

ParsedRecord = dict[str, Any]


@dataclass(frozen=True)
class SourceExtractionResult:
    """One fully parsed source and its uncommitted temporary artifact."""

    source_path: Path
    zip_member: str
    temp_path: Path | None
    selected_records: int
    parsed_records: int
    written_records: int
    metrics: B3ParserMetrics
    schema_fingerprint: str


class ZipProcessingResult(TypedDict):
    """Legacy-shaped mapping retained for internal test consumers."""

    records: int
    temp_file: str


class ExtractionSummary(TypedDict):
    """Aggregate result fields reported by the stable B3 use case."""

    total_files: int
    success_count: int
    error_count: int
    total_records: int
    errors: dict[str, str]
    output_file: str


ProcessSingleFileResult = tuple[str, ZipProcessingResult | Exception]
