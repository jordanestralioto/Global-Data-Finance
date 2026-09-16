"""User-friendly interface for downloading CVM fundamental stocks data.

This module provides a simple, high-level API for working with CVM
financial documents, making it easy to download and discover available data.

Example:
    >>> from datafin.cvm_docs import FundamentalStocksDataCVM
    >>>
    >>> # Initialize the client
    >>> cvm = FundamentalStocksDataCVM()
    >>>
    >>> # See available document types
    >>> docs = cvm.get_available_docs()
    >>> print(docs)
    >>>
    >>> # See available years
    >>> years = cvm.get_available_years()
    >>> print(years)
    >>>
    >>> # Download documents
    >>> result = cvm.download(
    ...     destination_path="/path/to/save",
    ...     list_docs=["DFP", "ITR"],
    ...     initial_year=2020,
    ...     last_year=2023
    ... )
    >>> print(
    ...     f"Downloaded {result.success_count_downloads} files successfully"
    ... )
"""

from ...brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    AvailableYearsInfoCVM,
    DownloadDocumentsUseCaseCVM,
    DownloadResultCVM,
    get_available_docs,
    get_available_years,
)
from ...core.archive_safety import ArchiveSafetyLimits
from ...core.config import Settings
from ...core.logging_config import get_logger
from .download_result_formatter import DownloadResultFormatter

logger = get_logger(__name__)


class FundamentalStocksDataCVM:
    """High-level interface for CVM fundamental stocks data operations.

    This class provides a simple API for downloading CVM financial documents
    and discovering available data. It uses AsyncDownloadAdapterCVM by default
    for 3-5x faster downloads compared to wget, with automatic retry logic.

    You can also customize the adapter:
    - AsyncDownloadAdapterCVM (default): Fast, no external dependencies

    Attributes:
        None - all dependencies are managed internally

    Example:
        >>> # Basic usage (uses ThreadPool by default)
        >>> cvm = FundamentalStocksDataCVM()
        >>>
        >>> # Download all document types for recent years
        >>> result = cvm.download(
        ...     destination_path="/home/user/cvm_data",
        ...     initial_year=2022
        ... )
        >>>
        >>> # Download specific documents
        >>> result = cvm.download(
        ...     destination_path="/home/user/cvm_data",
        ...     list_docs=["DFP"],
        ...     initial_year=2020,
        ...     last_year=2023
        ... )
        >>>
        >>> if result.error_count_downloads > 0:
        ...     print(f"Some downloads failed: {result.failed_downloads}")
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        """Initialize the FundamentalStocksDataCVM client.

        Args:
            settings: Immutable runtime settings snapshot. When omitted,
                a fresh :class:`~globaldatafinance.core.config.Settings`
                instance
                is constructed from current environment variables.
        """
        if settings is None:
            settings = Settings()
        self._settings = settings
        network_settings = self._settings.network
        archive_limits = ArchiveSafetyLimits.from_settings(
            self._settings.archive
        )
        allowed_unc_roots = self._settings.path_safety.allowed_unc_roots

        self.download_adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=None,
            timeout=network_settings.timeout,
            max_retries=network_settings.max_retries,
            backoff_multiplier=network_settings.retry_backoff,
            user_agent=network_settings.user_agent,
            archive_limits=archive_limits,
            allowed_unc_roots=allowed_unc_roots,
        )
        self.__download_use_case = DownloadDocumentsUseCaseCVM(
            self.download_adapter,
            allowed_unc_roots=allowed_unc_roots,
        )
        self.__result_formatter = DownloadResultFormatter(use_colors=True)

        logger.info(
            'FundamentalStocksDataCVM client initialized with '
            'AsyncDownloadAdapterCVM '
            '(automatic_extractor can be set per download call)'
        )

    @property
    def settings(self) -> Settings:
        """Return the immutable configuration snapshot used by this client."""
        return self._settings

    def download(
        self,
        destination_path: str,
        list_docs: list[str] | None = None,
        initial_year: int | None = None,
        last_year: int | None = None,
        automatic_extractor: bool = False,
    ) -> DownloadResultCVM:
        """Download CVM financial documents to a specified location.

        This method handles the complete download process, including:
        - Creating the destination directory if needed
        - Validating document types and year ranges
        - Downloading all requested documents with automatic retry
        - Optionally extracting downloaded files to Parquet format
        - Providing organized and easy-to-understand result display

        Args:
            destination_path: Directory path where files will be saved.
                             The directory will be created if it doesn't exist.
                             Example: "/home/user/cvm_data"
            list_docs: List of document type codes to download.
                      If None, downloads all available types.
                      Valid types: DFP, ITR, FCA, FRE, etc.
                      Example: ["DFP", "ITR"]
            initial_year: Starting year for downloads (inclusive).
                       If None, uses each document's minimum available year.
                       Example: 2020
            last_year: Ending year for downloads (inclusive).
                     If None, uses the current year.
                     Example: 2023
            automatic_extractor: If True, extracts downloaded ZIP files to
                                Parquet format. If False, keeps ZIP files.
                                Default: False (keeps original ZIP files).
                                Example: True

        Returns:
            DownloadResultCVM object containing:
            - success_count_downloads: Number of successfully downloaded files
            - error_count_downloads: Number of failed downloads
            - successful_downloads: Logical identifiers in ``{DOC}_{YEAR}``
                                   format, not filesystem paths
            - failed_downloads: Dictionary mapping ``{DOC}_{YEAR}`` identifiers
                                to error messages
            - Methods: add_success_downloads(), add_error_downloads()

        Raises:
            InvalidDocumentName: If an invalid document type is specified.
            InvalidFirstYear: If initial_year is outside valid range.
            InvalidLastYear: If last_year is outside valid range.
            ValueError: If destination_path is invalid.
            OSError: If directory cannot be created due to permissions.

        Example:
            >>> cvm = FundamentalStocksDataCVM()
            >>>
            >>> # Download documents without extraction (padrão)
            >>> result = cvm.download(
            ...     destination_path="/home/user/cvm_data",
            ...     initial_year=2022
            ... )
            >>>
            >>> # Download specific documents WITH extraction to Parquet
            >>> result = cvm.download(
            ...     destination_path="/home/user/dfp_data",
            ...     list_docs=["DFP"],
            ...     initial_year=2020,
            ...     last_year=2023,
            ...     automatic_extractor=True
            ... )
            >>>
            >>> # Check results programmatically
            >>> if result.error_count_downloads > 0:
            ...     print(f"Some downloads failed: {result.failed_downloads}")
        """
        if not isinstance(automatic_extractor, bool):
            raise TypeError(
                f'automatic_extractor must be a boolean (True or False), '
                f'got {type(automatic_extractor).__name__}: '
                f'{automatic_extractor!r}'
            )

        logger.info(
            'Download requested: path=%s, docs=%s, years=%s-%s, '
            'auto_extract=%s',
            destination_path,
            list_docs,
            initial_year,
            last_year,
            automatic_extractor,
        )

        result: DownloadResultCVM = self.__download_use_case.execute(
            destination_path=destination_path,
            list_docs=list_docs,
            initial_year=initial_year,
            last_year=last_year,
            automatic_extractor=automatic_extractor,
        )

        logger.info(
            'Download completed: %d successful, %d errors',
            result.success_count_downloads,
            result.error_count_downloads,
        )

        # Display formatted output
        self.__result_formatter.print_result(result)

        # Return the result for programmatic access
        return result

    async def async_download(
        self,
        destination_path: str,
        list_docs: list[str] | None = None,
        initial_year: int | None = None,
        last_year: int | None = None,
        automatic_extractor: bool = False,
    ) -> DownloadResultCVM:
        """Asynchronous variant of :meth:`download`.

        Same behavior and arguments as :meth:`download`, but awaits the
        download inside the caller's event loop instead of spinning a new
        one via ``asyncio.run``. Use this when composing CVM downloads into
        already-async code (the synchronous :meth:`download` raises
        ``RuntimeError`` if called from within a running loop).

        Example:
            >>> import asyncio
            >>> cvm = FundamentalStocksDataCVM()
            >>>
            >>> async def main():
            ...     return await cvm.async_download(
            ...         destination_path="/home/user/cvm_data",
            ...         list_docs=["DFP"],
            ...         initial_year=2022,
            ...     )
            >>>
            >>> result = asyncio.run(main())
        """
        if not isinstance(automatic_extractor, bool):
            raise TypeError(
                f'automatic_extractor must be a boolean (True or False), '
                f'got {type(automatic_extractor).__name__}: '
                f'{automatic_extractor!r}'
            )

        logger.info(
            'Async download requested: path=%s, docs=%s, years=%s-%s, '
            'auto_extract=%s',
            destination_path,
            list_docs,
            initial_year,
            last_year,
            automatic_extractor,
        )

        result: DownloadResultCVM = (
            await self.__download_use_case.execute_async(
                destination_path=destination_path,
                list_docs=list_docs,
                initial_year=initial_year,
                last_year=last_year,
                automatic_extractor=automatic_extractor,
            )
        )

        logger.info(
            'Async download completed: %d successful, %d errors',
            result.success_count_downloads,
            result.error_count_downloads,
        )

        self.__result_formatter.print_result(result)

        return result

    def get_available_docs(self) -> dict[str, str]:
        """Get all available CVM document types with descriptions.

        This method retrieves a mapping of document type codes to their
        full descriptions, helping you understand what data is available.

        Returns:
            Dictionary mapping document codes to descriptions.
            Example: {
                'DFP': 'Demonstração Financeira Padronizada',
                'ITR': 'Informação Trimestral',
                'FCA': 'Formulário Cadastral',
                ...
            }

        Example:
            >>> cvm = FundamentalStocksDataCVM()
            >>> docs = cvm.get_available_docs()
            >>>
            >>> # List all available document types
            >>> for code, description in docs.items():
            ...     print(f"{code}: {description}")
            >>>
            >>> # Check if a specific document type exists
            >>> if "DFP" in docs:
            ...     print(f"DFP available: {docs['DFP']}")
        """
        logger.debug('Retrieving available document types')
        result: dict[str, str] = get_available_docs()
        return result

    def get_available_years(self) -> AvailableYearsInfoCVM:
        """Get information about available years for CVM documents.

        This method returns the year ranges for which documents are available,
        including minimum years for document types and the current year.

        Returns:
            AvailableYearsInfoCVM named tuple with:
            - general_min_year: Minimum year for general documents (e.g., 2010)
            - itr_min_year: Minimum year for ITR documents (e.g., 2011)
            - cgvn_vlmo_min_year: Minimum year for CGVN/VLMO (e.g., 2018)
            - current_year: Current year (e.g., 2026)

        Example:
            >>> cvm = FundamentalStocksDataCVM()
            >>> years = cvm.get_available_years()
            >>>
            >>> # Access via typed attributes (IDE-friendly)
            >>> print(
            ...     f"General documents available from: "
            ...         f"{years.general_min_year}"
            ... )
            >>> print(f"ITR documents available from: {years.itr_min_year}")
            >>> print(f"Current year: {years.current_year}")
            >>>
            >>> # Dict escape hatch for backward compat
            >>> years_dict = years._asdict()
            >>>
            >>> # Use this info to make informed download requests
            >>> result = cvm.download(
            ...     destination_path="/data",
            ...     list_docs=["DFP"],
            ...     initial_year=years.general_min_year,
            ...     last_year=years.current_year
            ... )
        """
        logger.debug('Retrieving available years information')
        result: AvailableYearsInfoCVM = get_available_years()
        return result

    def __repr__(self) -> str:
        """Return a string representation of the client."""
        return 'FundamentalStocksDataCVM()'
