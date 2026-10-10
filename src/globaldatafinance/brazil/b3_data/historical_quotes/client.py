"""Orchestration layer for B3 historical quotes extraction.

The module keeps explicit use-case boundaries for the source facade and
delegates validation, filesystem access, parsing, and extraction to their
owning services.
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ....core.archive_safety import ArchiveSafetyLimits
from ....core.config import PathSafetySettings
from ....macro_exceptions import InvalidDestinationPathError
from .assets import AvailableAssetsServiceB3
from .cotahist_parser import CotahistParserB3
from .errors import (
    CotahistCatalogError,
    CotahistPreflightError,
    InvalidOutputFilename,
)
from .extraction_service import ExtractionServiceB3
from .filesystem import FileSystemServiceB3
from .input_validation import validate_and_resolve_cotahist_input
from .models import DocsToExtractorB3
from .preflight import resolve_extraction_sources
from .processing import ExtractionConfigServiceB3, ProcessingModeEnumB3
from .years import YearValidationServiceB3
from .zip_reader import ZipFileReaderB3


class GetAvailableAssetsUseCaseB3:
    """Expose the asset classes supported by the B3 source."""

    @staticmethod
    def execute() -> list[str]:
        """Get the list of available assets for historical quotes data."""
        return AvailableAssetsServiceB3.get_available_assets()


class GetAvailableYearsUseCaseB3:
    """Expose the current and earliest supported B3 years."""

    def get_current_year(self) -> int:
        """Get the current available year for historical quotes data."""
        return YearValidationServiceB3.get_current_year()

    def get_minimal_year(self) -> int:
        """Get the minimal available year for historical quotes data."""
        return YearValidationServiceB3.get_min_year()


class CreateRangeYearsUseCaseB3:
    """Use case for creating and validating a range of years."""

    @staticmethod
    def execute(initial_year: int, last_year: int) -> range:
        """Create and validate a range of years for data extraction."""
        year_range = YearValidationServiceB3.validate_and_create_year_range(
            initial_year, last_year
        )
        return year_range.to_range()


class CreateSetAssetsUseCaseB3:
    """Validate and normalize the requested B3 asset classes."""

    @staticmethod
    def execute(assets_list: list[str]) -> set[str]:
        """Create a set of available assets using AvailableAssetsServiceB3."""
        return AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )


class CreateSetToDownloadUseCaseB3:
    """Use case for finding COTAHIST ZIP or TXT inputs by year range."""

    @staticmethod
    def execute(
        range_years: range,
        path: str,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> set[str]:
        """Find all document files in the given path for the year range."""
        if not isinstance(path, str):
            raise TypeError(
                f'path_of_docs must be a string, got {type(path).__name__}'
            )

        if not path or path.isspace():
            raise InvalidDestinationPathError(
                'path_of_docs cannot be empty or whitespace'
            )

        file_system = FileSystemServiceB3(allowed_unc_roots=allowed_unc_roots)
        validated_path = file_system.validate_directory_path(path)
        return file_system.find_files_by_years(validated_path, range_years)


class ValidateCotahistInputUseCaseB3:
    """Validate one COTAHIST input before destination creation."""

    @staticmethod
    def execute(
        path: str | Path,
        *,
        limits: ArchiveSafetyLimits | None = None,
    ) -> str | None:
        """Validate an input archive or file and return the member name."""
        return validate_and_resolve_cotahist_input(path, limits=limits)


class VerifyDestinationPathsUseCaseB3:
    """Validate and prepare the destination directory for extraction."""

    @staticmethod
    def execute(
        destination_path: str,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> Path:
        """Return a safe, normalized destination path."""
        return FileSystemServiceB3(
            allowed_unc_roots=allowed_unc_roots
        ).prepare_destination_path(destination_path)

    @staticmethod
    def validate(
        destination_path: str,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> Path:
        """Validate a destination path without creating the directory."""
        return FileSystemServiceB3(
            allowed_unc_roots=allowed_unc_roots
        ).validate_destination_path(destination_path)


class ValidateExtractionConfigUseCaseB3:
    """Use case for validating extraction configuration."""

    @staticmethod
    def execute(processing_mode: str, output_filename: str) -> tuple[str, str]:
        """Validate processing mode and output filename."""
        valid_mode = ExtractionConfigServiceB3.validate_processing_mode(
            processing_mode
        )
        valid_filename = ExtractionConfigServiceB3.validate_output_filename(
            output_filename
        )
        return valid_mode, valid_filename


class CreateDocsToExtractUseCaseB3:
    """Create a DocsToExtractorB3 entity with validated parameters."""

    def __init__(
        self,
        path_of_docs: str,
        assets_list: list[str] | None,
        initial_year: int,
        last_year: int,
        destination_path: str | None = None,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
        limits: ArchiveSafetyLimits | None = None,
        processing_mode: ProcessingModeEnumB3 = ProcessingModeEnumB3.FAST,
        executor_backend: str = 'thread',
    ):
        """Store raw inputs before validating them in ``execute``."""
        if not isinstance(path_of_docs, str):
            raise TypeError(
                f'path_of_docs must be a string, got '
                f'{type(path_of_docs).__name__}'
            )

        if destination_path is not None and not isinstance(
            destination_path, str
        ):
            raise TypeError(
                f'destination_path must be a string, got '
                f'{type(destination_path).__name__}'
            )

        self.path_of_docs = path_of_docs
        self.assets_list = ['todos'] if assets_list is None else assets_list
        self.initial_year = initial_year
        self.last_year = last_year
        self.destination_path = (
            destination_path if destination_path else path_of_docs
        )
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        self.limits = limits
        self.processing_mode = processing_mode
        self.executor_backend = executor_backend

    def execute(self) -> DocsToExtractorB3:
        """Create and return a validated DocsToExtractorB3 entity."""
        set_assets = CreateSetAssetsUseCaseB3.execute(self.assets_list)

        range_years = CreateRangeYearsUseCaseB3.execute(
            self.initial_year, self.last_year
        )

        destination_paths = VerifyDestinationPathsUseCaseB3()
        validated_destination = destination_paths.validate(
            self.destination_path,
            allowed_unc_roots=self.allowed_unc_roots,
        )
        validated_source_directory = FileSystemServiceB3(
            allowed_unc_roots=self.allowed_unc_roots
        ).validate_directory_path(self.path_of_docs)
        all_markets = 'todos' in set_assets
        target_tpmerc_codes = (
            AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(set_assets)
        )
        try:
            catalog = resolve_extraction_sources(
                validated_source_directory,
                expected_years=range_years,
                target_tpmerc_codes=target_tpmerc_codes,
                all_markets=all_markets,
                limits=self.limits,
                processing_mode=self.processing_mode,
                executor_backend=self.executor_backend,
            )
        except CotahistCatalogError as error:
            raise CotahistPreflightError(
                str(error.source_path or validated_source_directory),
                error,
            ) from error
        documents_to_download = {
            str(source.path) for source in catalog.sources
        }
        if catalog.missing_years:
            normalized_destination = validated_destination
        else:
            normalized_destination = destination_paths.execute(
                str(validated_destination),
                allowed_unc_roots=self.allowed_unc_roots,
            )
        destination_path = (
            str(normalized_destination)
            if normalized_destination is not None
            else self.destination_path
        )

        return DocsToExtractorB3(
            path_of_docs=self.path_of_docs,
            set_assets=set_assets,
            range_years=range_years,
            destination_path=destination_path,
            documents_to_download=documents_to_download,
            all_markets=all_markets,
            target_tpmerc_codes=target_tpmerc_codes,
            requested_years=tuple(range_years),
            missing_years=catalog.missing_years,
            validated_sources=catalog.sources,
            ignored_duplicate_sources=catalog.ignored_duplicate_sources,
        )


class ExtractHistoricalQuotesUseCaseB3:
    """Main orchestrator for extracting historical quotes from COTAHIST files.

    Holds reusable reader and parser collaborators across calls.
    """

    def __init__(
        self,
        *,
        limits: ArchiveSafetyLimits | None = None,
        allowed_unc_roots: Sequence[str] | None = None,
        executor_backend: str = 'thread',
    ) -> None:
        """Initialize reusable reader and parser objects."""
        if executor_backend not in ('thread', 'process'):
            raise ValueError(
                f'Invalid executor_backend: {executor_backend!r}. '
                "Must be 'thread' or 'process'."
            )
        self.zip_reader = ZipFileReaderB3(limits=limits)
        self.parser = CotahistParserB3()
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        self.executor_backend = executor_backend
        self.last_phase_timings: dict[str, Any] = {}

    async def execute(
        self,
        docs_to_extract: DocsToExtractorB3,
        processing_mode: str = 'fast',
        output_filename: str = 'cotahist_extracted.parquet',
    ) -> dict[str, Any]:
        """Execute the extraction process."""
        self.last_phase_timings = {}
        mode = ProcessingModeEnumB3(processing_mode.lower())
        extraction_service = ExtractionServiceB3(
            zip_reader=self.zip_reader,
            parser=self.parser,
            processing_mode=mode,
            allowed_unc_roots=self.allowed_unc_roots,
            executor_backend=self.executor_backend,
        )

        target_tpmerc_codes = docs_to_extract.target_tpmerc_codes or (
            AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
                docs_to_extract.set_assets
            )
        )

        zip_files = docs_to_extract.documents_to_download

        output_path = Path(docs_to_extract.destination_path) / output_filename

        destination_resolved = Path(docs_to_extract.destination_path).resolve()
        output_resolved = output_path.resolve()
        if not output_resolved.is_relative_to(destination_resolved):
            raise InvalidOutputFilename(
                f'output path escapes destination: '
                f'{output_resolved} not under {destination_resolved}'
            )

        result = await extraction_service.extract_from_zip_files(
            zip_files=zip_files,
            target_tpmerc_codes=target_tpmerc_codes,
            output_path=output_path,
            validated_sources=(
                docs_to_extract.validated_sources
                if docs_to_extract.validated_sources
                or docs_to_extract.missing_years
                else None
            ),
            all_markets=docs_to_extract.all_markets,
            requested_years=(
                docs_to_extract.requested_years
                or tuple(docs_to_extract.range_years)
            ),
            missing_years=docs_to_extract.missing_years,
            asset_classes=sorted(docs_to_extract.set_assets),
            ignored_duplicate_sources=(
                docs_to_extract.ignored_duplicate_sources
            ),
        )
        self.last_phase_timings = extraction_service.last_phase_timings
        return result

    def execute_sync(
        self,
        docs_to_extract: DocsToExtractorB3,
        processing_mode: str = 'fast',
        output_filename: str = 'cotahist_extracted.parquet',
    ) -> dict[str, Any]:
        """Synchronous wrapper for execute()."""
        return asyncio.run(
            self.execute(docs_to_extract, processing_mode, output_filename)
        )
