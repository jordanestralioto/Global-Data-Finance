"""Coordinate B3 extraction preparation and result finalization."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from ....brazil.b3_data.historical_quotes import (
    CreateDocsToExtractUseCaseB3,
    DocsToExtractorB3,
    ExtractHistoricalQuotesUseCaseB3,
    GetAvailableYearsUseCaseB3,
    ValidateExtractionConfigUseCaseB3,
)
from ....brazil.b3_data.historical_quotes.assets import (
    AvailableAssetsServiceB3,
)
from ....brazil.b3_data.historical_quotes.async_execution import (
    run_blocking_phase,
)
from ....brazil.b3_data.historical_quotes.errors import CotahistPreflightError
from ....brazil.b3_data.historical_quotes.integrity_report import (
    build_integrity_report,
)
from ....brazil.b3_data.historical_quotes.models import (
    CotahistCatalogResolution,
)
from ....brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from ....core.archive_safety import ArchiveSafetyLimits
from ....core.config import Settings
from ....core.logging_config import get_logger
from ....macro_exceptions import CorruptedZipError, ExtractionError
from ..extraction_result_formatter import ExtractionResultFormatter
from ..result_formatters import HistoricalQuotesResultFormatter
from ..types import B3IntegrityReport, ExtractionResultB3

logger = get_logger(__name__)


class ExtractionFlowB3:
    """Prepare B3 extraction requests and finalize their public results."""

    def __init__(
        self,
        *,
        extract_use_case: ExtractHistoricalQuotesUseCaseB3,
        available_years_use_case: GetAvailableYearsUseCaseB3,
        settings: Settings,
        allowed_unc_roots: Sequence[str] | None,
    ) -> None:
        """Store facade collaborators used across extraction requests."""
        self._extract_use_case = extract_use_case
        self._available_years_use_case = available_years_use_case
        self._settings = settings
        self._allowed_unc_roots = allowed_unc_roots
        self._validate_config_use_case = ValidateExtractionConfigUseCaseB3()
        self._result_formatter = ExtractionResultFormatter(use_colors=True)

    async def execute(
        self,
        *,
        path_of_docs: str,
        assets_list: list[str] | None,
        initial_year: int | None,
        last_year: int | None,
        destination_path: str | None,
        output_filename: str,
        processing_mode: str,
        verbose: bool,
    ) -> ExtractionResultB3:
        """Run preparation, extraction, and stable result formatting."""
        start_time = time.time()
        resolved_assets = ['todos'] if assets_list is None else assets_list
        try:
            (
                docs_to_extract,
                processing_mode,
                output_filename_with_ext,
            ) = await run_blocking_phase(
                self._prepare_extraction,
                path_of_docs=path_of_docs,
                assets_list=resolved_assets,
                initial_year=initial_year,
                last_year=last_year,
                destination_path=destination_path,
                output_filename=output_filename,
                processing_mode=processing_mode,
            )
        except (CorruptedZipError, ExtractionError) as error:
            return self._finalize_result(
                result=self._preflight_failure_result(
                    error,
                    resolved_assets,
                    initial_year=initial_year,
                    last_year=last_year,
                ),
                assets_list=resolved_assets,
                processing_mode=processing_mode,
                elapsed_time=time.time() - start_time,
                verbose=verbose,
            )

        result = await self._extract_use_case.execute(
            docs_to_extract=docs_to_extract,
            processing_mode=processing_mode,
            output_filename=output_filename_with_ext,
        )
        return self._finalize_result(
            result=result,
            assets_list=resolved_assets,
            processing_mode=processing_mode,
            elapsed_time=time.time() - start_time,
            verbose=verbose,
        )

    def _preflight_failure_result(
        self,
        error: CorruptedZipError | ExtractionError,
        assets: list[str],
        *,
        initial_year: int | None,
        last_year: int | None,
    ) -> dict[str, Any]:
        """Report observed sources and coverage without claiming a commit."""
        resolution = (
            error.resolution
            if isinstance(error, CotahistPreflightError)
            else CotahistCatalogResolution((), ())
        )
        asset_classes = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets
        )
        filename = (
            Path(error.path).name
            if hasattr(error, 'path') and error.path
            else 'input'
        )
        error_type = (
            'ExtractionError'
            if isinstance(error, CotahistPreflightError)
            else type(error).__name__
        )
        return {
            'total_files': error.resolved_file_count
            if isinstance(error, CotahistPreflightError)
            else 0,
            'success_count': 0,
            'error_count': 1,
            'total_records': 0,
            'errors': {filename: f'{error_type}: {error}'},
            'output_file': '',
            'schema_version': 2,
            'integrity': cast(
                B3IntegrityReport,
                build_integrity_report(
                    status='failed',
                    requested_years=self._requested_years(
                        initial_year, last_year
                    ),
                    selected_sources=resolution.sources,
                    missing_years=resolution.missing_years,
                    complete_market_selection='todos' in asset_classes,
                    market_codes=sorted(
                        AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
                            asset_classes
                        )
                    ),
                    asset_classes=sorted(asset_classes),
                    ignored_duplicate_sources=(
                        resolution.ignored_duplicate_sources
                    ),
                ),
            ),
        }

    def _requested_years(
        self,
        initial_year: int | None,
        last_year: int | None,
    ) -> list[int]:
        """Resolve the public default year span for preflight error reports."""
        first = self._resolve_initial_year(initial_year)
        last = self._resolve_last_year(last_year)
        if first > last:
            return []
        return list(range(first, last + 1))

    def _prepare_extraction(
        self,
        *,
        path_of_docs: str,
        assets_list: list[str],
        initial_year: int | None,
        last_year: int | None,
        destination_path: str | None,
        output_filename: str,
        processing_mode: str,
    ) -> tuple[DocsToExtractorB3, str, str]:
        """Validate request options and build the extraction input model."""
        initial_year = self._resolve_initial_year(initial_year)
        last_year = self._resolve_last_year(last_year)
        processing_mode, output_filename_with_ext = (
            self._validate_config_use_case.execute(
                processing_mode=processing_mode,
                output_filename=output_filename,
            )
        )

        logger.info(
            f'Extraction requested: path={path_of_docs}, '
            f'destination={destination_path or path_of_docs}, '
            f'assets={assets_list}, years={initial_year}-{last_year}, '
            f'mode={processing_mode}'
        )
        preflight_options: dict[str, Any] = {}
        if (
            processing_mode == 'fast'
            and self._extract_use_case.executor_backend == 'process'
        ):
            preflight_options = {
                'processing_mode': ProcessingModeEnumB3.FAST,
                'executor_backend': 'process',
            }
        docs_to_extract = CreateDocsToExtractUseCaseB3(
            path_of_docs=path_of_docs,
            assets_list=assets_list,
            initial_year=initial_year,
            last_year=last_year,
            destination_path=destination_path,
            allowed_unc_roots=self._allowed_unc_roots,
            limits=ArchiveSafetyLimits.from_settings(self._settings.archive),
            **preflight_options,
        ).execute()
        logger.info(
            f'Found {len(docs_to_extract.documents_to_download)} COTAHIST '
            'input files to process'
        )
        return docs_to_extract, processing_mode, output_filename_with_ext

    def _finalize_result(
        self,
        *,
        result: dict[str, Any],
        assets_list: list[str],
        processing_mode: str,
        elapsed_time: float,
        verbose: bool,
    ) -> ExtractionResultB3:
        """Enrich, log, and optionally present an extraction result."""
        result['assets'] = assets_list
        result['processing_mode'] = processing_mode
        result['elapsed_time'] = elapsed_time
        enriched = HistoricalQuotesResultFormatter.enrich_result(result)
        logger.info(
            f'Extraction completed: {result["success_count"]} successful, '
            f'{result["error_count"]} errors, '
            f'{result["total_records"]} records extracted'
        )
        if verbose:
            self._result_formatter.print_result(result)
        return enriched

    def _resolve_initial_year(self, initial_year: int | None) -> int:
        """Resolve initial_year, falling back to the minimum year."""
        if initial_year is None:
            resolved = self._available_years_use_case.get_minimal_year()
            logger.debug('initial_year omitted, using min: %s', resolved)
            return resolved
        return initial_year

    def _resolve_last_year(self, last_year: int | None) -> int:
        """Resolve last_year, falling back to the current year."""
        if last_year is None:
            resolved = self._available_years_use_case.get_current_year()
            logger.debug('last_year omitted, using current: %s', resolved)
            return resolved
        return last_year
