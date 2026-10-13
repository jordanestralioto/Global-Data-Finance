"""CVM-owned orchestration of exact CSV-to-Parquet preservation."""

from __future__ import annotations

import zipfile
from pathlib import Path

from .....core.archive_safety import ArchiveSafetyLimits
from ..source_inventory import archive_fingerprint
from .models import CsvPipelineResult
from .source import ReopenableCsvSource, detect_encoding, prepare_utf8_source


class CvmCsvParquetPipeline:
    """Preserve one complete CVM CSV member through explicit text schemas."""

    def __init__(
        self,
        source_path: str | Path,
        csv_member: str,
        *,
        limits: ArchiveSafetyLimits | None = None,
        source_sha256: str | None = None,
        archive: zipfile.ZipFile | None = None,
    ) -> None:
        """Store the reopenable source used by all pipeline passes."""
        self.source = ReopenableCsvSource(
            source_path, csv_member, limits=limits, archive=archive
        )
        self.source_sha256 = source_sha256

    def convert(
        self, *, staged_path: Path, staging_dir: Path
    ) -> CsvPipelineResult:
        """Write one staged Parquet after global analysis and validation."""
        with self.source.open_archive() as archive:
            source = ReopenableCsvSource(
                self.source.source_path,
                self.source.member_name,
                limits=self.source.limits,
                archive=archive,
            )
            fingerprint = self.source_sha256 or archive_fingerprint(
                source.source_path, archive
            )
            return self._convert_source(
                source, fingerprint, staged_path, staging_dir
            )

    @staticmethod
    def _convert_source(
        source: ReopenableCsvSource,
        fingerprint: str,
        staged_path: Path,
        staging_dir: Path,
    ) -> CsvPipelineResult:
        """Apply the exact-text contract to one stable bounded member."""
        from .inference import (
            analyse_csv,
            build_schema,
            normalize_short_rows,
        )
        from .writer import write_parquet

        plan = detect_encoding(source)
        utf8_source = prepare_utf8_source(source, plan, staging_dir)
        analysis = analyse_csv(source, utf8_source, plan)
        if analysis.short_rows_seen:
            normalized = normalize_short_rows(
                source,
                utf8_source,
                plan,
                staging_dir,
                analysis.header,
            )
            analysis.normalized_path = normalized
        schema = build_schema(analysis)
        schema = schema.with_metadata(
            {
                **(schema.metadata or {}),
                b'cvm.source-archive': source.source_path.name.encode('utf-8'),
                b'cvm.source-archive-sha256': fingerprint.encode('ascii'),
                b'cvm.source-member': source.member_name.encode('utf-8'),
                b'cvm.source-encoding': plan.encoding.encode('ascii'),
            }
        )
        return write_parquet(
            source,
            analysis.normalized_path or utf8_source,
            plan,
            staged_path,
            analysis,
            schema,
        )
