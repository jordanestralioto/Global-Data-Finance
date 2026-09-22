"""High-level API for extracting B3 COTAHIST quotes to Parquet.

See :class:`HistoricalQuotesB3` and the docs site (``docs/user-guide``) for
usage. Quick start::

    from globaldatafinance import HistoricalQuotesB3

    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="/path/to/cotahist_zips", assets_list=["ações", "etf"],
        initial_year=2020, last_year=2023,
    )
"""

import asyncio
import os
import time
from typing import Any

from ...brazil.b3_data.historical_quotes import (
    CreateDocsToExtractUseCaseB3,
    DocsToExtractorB3,
    ExtractHistoricalQuotesUseCaseB3,
    GetAvailableAssetsUseCaseB3,
    GetAvailableYearsUseCaseB3,
    ValidateExtractionConfigUseCaseB3,
)
from ...core.archive_safety import ArchiveSafetyLimits
from ...core.config import Settings
from ...core.logging_config import get_logger
from .extraction_result_formatter import ExtractionResultFormatter
from .result_formatters import HistoricalQuotesResultFormatter
from .types import ExtractionResultB3

logger = get_logger(__name__)


class HistoricalQuotesB3:
    """High-level interface for B3 historical quotes extraction operations.

    This class provides a simple API for extracting historical stock quotes
    from B3 COTAHIST archives (ZIP or TXT) and converting them to Parquet.

    The extraction process supports two processing modes:
    - Fast mode: High performance with higher CPU/RAM usage (recommended)
    - Slow mode: Resource-efficient with lower CPU/RAM usage.

    Supported asset classes:
    - 'ações': Stocks (cash and fractional market)
    - 'etf': Exchange Traded Funds

    Attributes:
        None - all dependencies are managed internally

    Example:
        >>> b3 = HistoricalQuotesB3()
        >>> result = b3.extract(
        ...     path_of_docs="/data/cotahist",
        ...     destination_path="/data/output",
        ...     assets_list=["ações", "etf"],
        ...     initial_year=2022,
        ... )
        >>> if not result['success']:
        ...     print(f"Extraction had errors: {result['message']}")
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        """Initialize the HistoricalQuotesB3 client.

        Args:
            settings: Immutable runtime settings snapshot. When omitted,
                a fresh :class:`~globaldatafinance.core.config.Settings`
                instance is constructed from current environment variables.
        """
        backend = os.environ.get('GDF_B3_EXECUTOR_BACKEND', 'thread')
        if backend not in ('thread', 'process'):
            raise ValueError(
                f'Invalid executor_backend: {backend!r}. '
                "Must be 'thread' or 'process'."
            )
        self._settings = settings if settings is not None else Settings()
        limits = ArchiveSafetyLimits.from_settings(self._settings.archive)
        self._allowed_unc_roots = self._settings.path_safety.allowed_unc_roots

        self._extract_use_case = ExtractHistoricalQuotesUseCaseB3(
            limits=limits,
            allowed_unc_roots=self._allowed_unc_roots,
            executor_backend=backend,
        )
        self._available_assets_use_case = GetAvailableAssetsUseCaseB3()
        self._available_years_use_case = GetAvailableYearsUseCaseB3()
        self._validate_config_use_case = ValidateExtractionConfigUseCaseB3()
        self._result_formatter = ExtractionResultFormatter(use_colors=True)

        logger.info('HistoricalQuotesB3 initialized (backend=%s)', backend)

    @property
    def settings(self) -> Settings:
        """Return the immutable configuration snapshot used by this client."""
        return self._settings

    @property
    def _last_phase_timings(self) -> dict[str, Any]:
        """Return private benchmark telemetry from the last extraction run."""
        return self._extract_use_case.last_phase_timings

    def extract(
        self,
        path_of_docs: str,
        assets_list: list[str],
        initial_year: int | None = None,
        last_year: int | None = None,
        destination_path: str | None = None,
        output_filename: str = 'cotahist_extracted',
        processing_mode: str = 'fast',
        verbose: bool = True,
    ) -> ExtractionResultB3:
        r"""Extract historical quotes from COTAHIST archives to Parquet.

        Validates the asset classes and year range, finds the matching
        COTAHIST files (ZIP or TXT), parses and filters them, and writes the
        result to a Parquet file.

        Args:
            path_of_docs: Directory path where COTAHIST files reside
                         (`COTAHIST_A{YYYY}.ZIP` or `COTAHIST_A{YYYY}.TXT`).
                         Example: "/home/user/cotahist_files"
            assets_list: List of asset class codes to extract.
                        Valid values: 'ações', 'etf', 'opções', 'termo',
                                     'exercicio_opcoes', 'forward', 'leilao'
            initial_year: Starting year (inclusive, >= 1986). Defaults to 1986.
            last_year: Ending year (inclusive). Defaults to current year.
            destination_path: Directory path for the generated Parquet file.
                            If None, uses path_of_docs as destination.
            output_filename: Required output basename without path separators.
                           The optional ``.parquet`` suffix is accepted and
                           is appended automatically only when it is absent.
                           Default: "cotahist_extracted"
            processing_mode: 'fast' (high performance) or 'slow' (low RAM).
            verbose: When True (default), print summary to stdout.

        Note:
            Synchronous wrapper around :meth:`extract_async` using ``asyncio``.

        Returns:
            ExtractionResultB3 TypedDict containing:
            - success (bool): True if extraction completed without errors
            - message (str): Human-readable summary of the extraction
            - total_files (int): Number of input files processed (ZIP or TXT)
            - success_count (int): Number of successfully processed files
            - error_count (int): Number of files that failed to process
            - total_records (int): Total number of records extracted
            - output_file (str): Path to the generated Parquet file
            - errors (dict[str, str]): Failed files mapped to error messages
            - assets (list[str]): Asset classes filtered during extraction
            - processing_mode (str): Processing mode ('fast' or 'slow')
            - elapsed_time (float): Total elapsed execution duration in seconds

        Raises:
            EmptyAssetListError: If assets_list is empty or not a list.
            InvalidAssetsName: If any asset class in assets_list is invalid.
            InvalidFirstYear: If initial_year is outside 1986-current year.
            InvalidLastYear: If last_year is outside range or < initial_year.
            ValueError: If path_of_docs is invalid.
            OSError: If directories cannot be created or accessed.

        Example:
            >>> b3 = HistoricalQuotesB3()
            >>> result = b3.extract(
            ...     path_of_docs="/data/cotahist",
            ...     destination_path="/data/output",
            ...     assets_list=["ações", "etf"],
            ...     initial_year=2020,
            ...     last_year=2023,
            ... )
            >>> if result['success']:
            ...     print(f"Extracted {result['total_records']} records")
        """
        return asyncio.run(
            self.extract_async(
                path_of_docs=path_of_docs,
                assets_list=assets_list,
                initial_year=initial_year,
                last_year=last_year,
                destination_path=destination_path,
                output_filename=output_filename,
                processing_mode=processing_mode,
                verbose=verbose,
            )
        )

    async def extract_async(
        self,
        path_of_docs: str,
        assets_list: list[str],
        initial_year: int | None = None,
        last_year: int | None = None,
        destination_path: str | None = None,
        output_filename: str = 'cotahist_extracted',
        processing_mode: str = 'fast',
        verbose: bool = True,
    ) -> ExtractionResultB3:
        """Async counterpart of :meth:`extract`.

        Use this when calling from inside an already-running event loop, where
        the synchronous :meth:`extract` (which calls ``asyncio.run``) would
        raise ``RuntimeError``. Arguments and return value are identical to
        :meth:`extract`; see that method for full documentation.
        """
        docs_to_extract, processing_mode, output_filename_with_ext = (
            self._prepare_extraction(
                path_of_docs=path_of_docs,
                assets_list=assets_list,
                initial_year=initial_year,
                last_year=last_year,
                destination_path=destination_path,
                output_filename=output_filename,
                processing_mode=processing_mode,
            )
        )

        start_time = time.time()

        result = await self._extract_use_case.execute(
            docs_to_extract=docs_to_extract,
            processing_mode=processing_mode,
            output_filename=output_filename_with_ext,
        )

        elapsed_time = time.time() - start_time

        return self._finalize_result(
            result=result,
            assets_list=assets_list,
            processing_mode=processing_mode,
            elapsed_time=elapsed_time,
            verbose=verbose,
        )

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
        """Validate config and build the extraction request (no I/O parsing).

        Shared by the sync and async entrypoints. Returns the documents to
        extract, the normalized processing mode, and the output filename with
        the ``.parquet`` extension applied.
        """
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

        docs_to_extract: DocsToExtractorB3 = CreateDocsToExtractUseCaseB3(
            path_of_docs=path_of_docs,
            assets_list=assets_list,
            initial_year=initial_year,
            last_year=last_year,
            destination_path=destination_path,
            allowed_unc_roots=self._allowed_unc_roots,
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
        """Enrich the raw result, log a summary, and optionally print it."""
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

    def get_available_assets(self) -> list[str]:
        """Get all available B3 asset classes that can be extracted.

        This method retrieves a list of supported asset class codes
        that can be used in the assets_list parameter of extract().

        Returns:
            List of available asset class codes:
            - 'ações': Stocks (cash and fractional market)
            - 'etf': Exchange Traded Funds
            - 'opções': Options (call and put)
            - 'termo': Term market
            - 'exercicio_opcoes': Options exercise
            - 'forward': Forward market
            - 'leilao': Auction market

        Example:
            >>> b3 = HistoricalQuotesB3()
            >>> assets = b3.get_available_assets()
            >>> "ações" in assets
            True
        """
        logger.debug('Retrieving available asset classes')
        return self._available_assets_use_case.execute()

    def get_available_years(self) -> dict[str, int]:
        """Get information about available years for B3 historical data.

        This method returns the available COTAHIST year range.
        B3 historical quotes data is available from 1986 to the current year.

        Returns:
            Dictionary with year information:
            - 'minimal_year': Minimum year available (1986)
            - 'current_year': Current year (maximum year available)

        Example:
            >>> b3 = HistoricalQuotesB3()
            >>> years = b3.get_available_years()
            >>> years['minimal_year'], years['current_year']
            (1986, 2025)
        """
        logger.debug('Retrieving available years information')
        return {
            'minimal_year': self._available_years_use_case.get_minimal_year(),
            'current_year': self._available_years_use_case.get_current_year(),
        }

    def __repr__(self) -> str:
        """Return a string representation of the client."""
        return 'HistoricalQuotesB3()'

    def _resolve_initial_year(self, initial_year: int | None) -> int:
        """Resolve initial_year, falling back to minimal year if omitted."""
        if initial_year is None:
            resolved = self._available_years_use_case.get_minimal_year()
            logger.debug('initial_year omitted, using min: %s', resolved)
            return resolved
        return initial_year

    def _resolve_last_year(self, last_year: int | None) -> int:
        """Resolve last_year, falling back to current year if omitted."""
        if last_year is None:
            resolved = self._available_years_use_case.get_current_year()
            logger.debug('last_year omitted, using current: %s', resolved)
            return resolved
        return last_year
