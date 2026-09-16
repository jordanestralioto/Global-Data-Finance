"""CVM-owned orchestration of the two-pass CSV-to-Parquet conversion."""

from __future__ import annotations

from pathlib import Path

from .....core.archive_safety import ArchiveSafetyLimits
from .models import CsvPipelineResult
from .source import ReopenableCsvSource, detect_encoding, prepare_utf8_source


class CvmCsvParquetPipeline:
    """Infer and write one CVM CSV member through explicit Arrow schemas."""

    def __init__(
        self,
        source_path: str | Path,
        csv_member: str,
        *,
        limits: ArchiveSafetyLimits | None = None,
    ) -> None:
        """Store the reopenable source used by all pipeline passes."""
        self.source = ReopenableCsvSource(
            source_path, csv_member, limits=limits
        )

    def convert(
        self, *, staged_path: Path, staging_dir: Path
    ) -> CsvPipelineResult:
        """Write one staged Parquet after global analysis and validation."""
        from .inference import (
            analyse_csv,
            build_schema,
            normalize_short_rows,
        )
        from .writer import write_parquet

        plan = detect_encoding(self.source)
        utf8_source = prepare_utf8_source(self.source, plan, staging_dir)
        analysis = analyse_csv(self.source, utf8_source, plan)
        if analysis.short_rows_seen:
            normalized = normalize_short_rows(
                self.source,
                utf8_source,
                plan,
                staging_dir,
                analysis.header,
            )
            analysis = analyse_csv(self.source, normalized, plan)
            analysis.normalized_path = normalized
        schema = build_schema(analysis)
        return write_parquet(
            self.source,
            analysis.normalized_path or utf8_source,
            plan,
            staged_path,
            analysis,
            schema,
        )
