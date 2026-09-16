"""CVM orchestration for validated, transactional Arrow extraction."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....core.config import PathSafetySettings
from ....macro_exceptions import CorruptedZipError, ExtractionError
from ....macro_infra.transactional_publication import TransactionalPublisher
from .csv_pipeline import CvmCsvParquetPipeline


@dataclass(frozen=True)
class _CvmOutput:
    """One safe CSV member mapped to its established output basename."""

    csv_member: str
    parquet_name: str
    final_path: Path
    source_bytes: int


class CvmFailureAtomicBatchCommit:
    """Stage every CVM CSV through Arrow before a recoverable batch commit."""

    def __init__(
        self,
        source_path: str,
        destination_path: str,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> None:
        """Store the source-owned paths for one recoverable batch."""
        self.source_path = source_path
        self.destination_path = destination_path
        if archive_limits is None:
            archive_limits = ArchiveSafetyLimits.from_environment()
        self.archive_limits = archive_limits
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )

    def execute(self, zip_file: zipfile.ZipFile) -> int:
        """Convert all CSV members and atomically publish their Parquets."""
        publisher = TransactionalPublisher(
            self.destination_path,
            owner='cvm',
            source_path=self.source_path,
            allowed_unc_roots=self.allowed_unc_roots,
        )
        publisher.validate_destination()
        self.destination_path = str(publisher.destination_dir)
        outputs = self._build_outputs(zip_file)
        source_size = sum(output.source_bytes for output in outputs)
        publication = publisher.begin(
            source_descriptors=[
                {
                    'source': Path(self.source_path).name,
                    'member_count': str(len(outputs)),
                }
            ],
            required_bytes=source_size,
        )
        try:
            for output in outputs:
                staged_path = publication.stage_path(output.parquet_name)
                result = CvmCsvParquetPipeline(
                    self.source_path,
                    output.csv_member,
                    limits=self.archive_limits,
                ).convert(
                    staged_path=staged_path,
                    staging_dir=publication.staging_dir,
                )
                publication.add_artifact(
                    final_path=output.final_path,
                    staged_path=staged_path,
                    expected_rows=result.rows,
                    schema_fingerprint=result.schema_fingerprint,
                )
            publication.mark_validated()
            publication.commit()
        except Exception as error:
            try:
                publication.abort()
            except (ExtractionError, OSError) as rollback_error:
                raise ExtractionError(
                    self.source_path,
                    'CVM extraction failed and transaction cleanup also '
                    f'failed: {type(rollback_error).__name__}: '
                    f'{rollback_error}',
                ) from error
            raise
        return len(outputs)

    def _build_outputs(self, zip_file: zipfile.ZipFile) -> list[_CvmOutput]:
        """Validate every CSV source and reject basename collisions early."""
        try:
            infos = validate_zip_archive(
                self.source_path, zip_file, limits=self.archive_limits
            )
            validate_zip_crc_with_limits(
                self.source_path,
                zip_file,
                limits=self.archive_limits,
                infos=infos,
            )
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(self.source_path, str(error)) from error

        csv_infos = [
            info
            for info in infos
            if not info.is_dir() and info.filename.lower().endswith('.csv')
        ]
        if not csv_infos:
            raise ExtractionError(
                self.source_path, 'Archive does not contain any CSV members'
            )

        names: set[str] = set()
        outputs: list[_CvmOutput] = []
        for info in sorted(
            csv_infos,
            key=lambda item: item.filename.casefold(),
        ):
            parquet_name = self._parquet_basename(info.filename)
            normalized = parquet_name.casefold()
            if normalized in names:
                raise ExtractionError(
                    self.source_path,
                    'CSV members collide after basename normalization: '
                    f'{info.filename!r} -> {parquet_name!r}',
                )
            names.add(normalized)
            outputs.append(
                _CvmOutput(
                    csv_member=info.filename,
                    parquet_name=parquet_name,
                    final_path=Path(self.destination_path) / parquet_name,
                    source_bytes=info.file_size,
                )
            )
        return outputs

    @staticmethod
    def _parquet_basename(csv_member: str) -> str:
        """Keep the established basename-only output naming contract."""
        name = PurePosixPath(csv_member.replace('\\', '/')).name
        return f'{PurePosixPath(name).stem}.parquet'
