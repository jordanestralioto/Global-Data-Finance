"""CVM download orchestration and caller-destination safety boundary."""

import time
from collections.abc import Sequence
from pathlib import Path

from ....core import get_logger
from ....core.config import PathSafetySettings
from ....core.utils.destination_paths import (
    normalize_destination_path,
    prepare_writable_destination,
)
from . import core
from .errors import EmptyDocumentListError, MissingDownloadUrlError
from .http import AsyncDownloadAdapterCVM

logger = get_logger(__name__)


def get_available_docs() -> dict[str, str]:
    """Retrieve available document types."""
    logger.info('Retrieving available document types')
    docs = core.get_available_docs()
    logger.debug('Retrieved %d document types', len(docs))
    return docs


def get_available_years() -> core.AvailableYearsInfoCVM:
    """Retrieve available years information."""
    logger.info('Retrieving available years information')
    available_years = core.AvailableYearsCVM()
    years_info = core.AvailableYearsInfoCVM(
        general_min_year=available_years.get_minimal_general_year(),
        itr_min_year=available_years.get_minimal_itr_year(),
        cgvn_vlmo_min_year=available_years.get_minimal_cgvn_vlmo_year(),
        current_year=available_years.get_current_year(),
    )
    logger.debug('Retrieved years information: %s', years_info)
    return years_info


def generate_range_years(
    initial_year: int | None = None,
    last_year: int | None = None,
) -> range:
    """Generate an inclusive range of years."""
    logger.debug(
        'Generating Range Years, years=%s-%s', initial_year, last_year
    )
    range_years = core.AvailableYearsCVM().return_range_years(
        initial_year=initial_year, last_year=last_year
    )
    logger.debug('Generated range of years: %s', list(range_years))
    return range_years


def generate_urls(
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
) -> tuple[dict[str, list[str]], set[str]]:
    """Generate download URLs for specified documents and years."""
    logger.debug(
        'Generating URLs for docs=%s, years=%s-%s',
        list_docs,
        initial_year,
        last_year,
    )
    dict_zips, new_set_docs = (
        core.DictZipsToDownloadCVM().get_dict_zips_to_download(
            list_docs=list_docs,
            initial_year=initial_year,
            last_year=last_year,
        )
    )
    total_urls = sum(len(urls) for urls in dict_zips.values())
    logger.debug(
        'Generated %d URLs from %d document types', total_urls, len(dict_zips)
    )
    return dict_zips, new_set_docs


class VerifyPathsUseCasesCVM:
    """Verify and create destination directory structure for CVM downloads.

    Path-traversal defense (R11) delegates to the shared
    :func:`globaldatafinance.core.utils.assert_path_not_sensitive` helper
    so the CVM and B3 facades enforce the same blocklist with the same
    path-aware semantics. The check runs **before** any ``mkdir``.
    """

    def __init__(
        self,
        destination_path: str,
        new_set_docs: set[str],
        range_years: range,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ):
        """Initialize the destination and requested document-year scope."""
        self.destination_path = destination_path
        self.new_set_docs = new_set_docs
        self.range_years = range_years
        self.allowed_unc_roots = PathSafetySettings.resolve_allowed_unc_roots(
            allowed_unc_roots
        )
        self.__available_years = core.AvailableYearsCVM()

        if not new_set_docs:
            raise EmptyDocumentListError()

        logger.debug(
            'VerifyPathsUseCasesCVM created: path=%s, docs=%s',
            self.destination_path,
            self.new_set_docs,
        )

    def execute(self) -> dict[str, dict[int, str]]:
        """Create and verify directory structure for documents and years."""
        normalize_destination_path(
            self.destination_path,
            type_label='Destination path',
            empty_message='path cannot be empty or whitespace',
            allowed_unc_roots=self.allowed_unc_roots,
        )
        docs_paths: dict[str, dict[int, str]] = {}
        for doc in self.new_set_docs:
            doc_path = str(Path(self.destination_path) / doc)
            validated_doc_path = self.__validate_and_create_paths(doc_path)

            docs_paths[doc] = {}
            for year in self.range_years:
                is_valid = self.__is_valid_year_for_doc(doc, year)
                if not is_valid:
                    logger.debug(
                        'Skipping folder for doc=%s, year=%s '
                        '(invalid year for this document)',
                        doc,
                        year,
                    )
                    continue
                year_path = str(Path(validated_doc_path) / str(year))
                validated_year_path = self.__validate_and_create_paths(
                    year_path
                )
                docs_paths[doc][year] = validated_year_path

        logger.debug(
            'Directory structure created successfully. Documents: %d, '
            'Years per document: %s',
            len(docs_paths),
            [len(years) for years in docs_paths.values()],
        )

        return docs_paths

    def __is_valid_year_for_doc(self, doc: str, year: int) -> bool:
        doc_upper = doc.upper()
        if doc_upper == 'ITR':
            return year >= self.__available_years.get_minimal_itr_year()
        if doc_upper in {'VLMO', 'CGVN'}:
            return year >= self.__available_years.get_minimal_cgvn_vlmo_year()
        return year >= self.__available_years.get_minimal_general_year()

    def __validate_and_create_paths(self, path: str) -> str:
        result = prepare_writable_destination(
            path,
            type_label='Destination path',
            empty_message='path cannot be empty or whitespace',
            allowed_unc_roots=self.allowed_unc_roots,
        )
        logger.debug('Destination path validated and ready: %s', result)
        return str(result)


class DownloadDocumentsUseCaseCVM:
    """Orchestrate CVM document downloads through one adapter."""

    def __init__(
        self,
        repository: AsyncDownloadAdapterCVM,
        *,
        allowed_unc_roots: Sequence[str] | None = None,
    ) -> None:
        """Initialize the orchestrator with its repository collaborator."""
        self.__repository: AsyncDownloadAdapterCVM = repository
        self.__allowed_unc_roots = (
            PathSafetySettings.resolve_allowed_unc_roots(allowed_unc_roots)
        )

        logger.debug(
            'DownloadDocumentsUseCaseCVM initialized with repository=%s',
            repository.__class__.__name__,
        )

    def execute(
        self,
        destination_path: str,
        list_docs: list[str] | None = None,
        initial_year: int | None = None,
        last_year: int | None = None,
        *,
        automatic_extractor: bool = False,
    ) -> core.DownloadResultCVM:
        """Execute the download operation (synchronous)."""
        dict_urls_zips, docs_paths = self.__prepare_inputs(
            destination_path, list_docs, initial_year, last_year
        )

        start_time = time.time()

        try:
            tasks = self.__prepare_download_tasks(dict_urls_zips, docs_paths)
            result = self.__repository.download_docs(
                tasks, automatic_extractor=automatic_extractor
            )
            return self.__finalize(result, start_time)

        except Exception as e:
            logger.error(f'Download execution failed: {e}', exc_info=True)
            raise

    async def execute_async(
        self,
        destination_path: str,
        list_docs: list[str] | None = None,
        initial_year: int | None = None,
        last_year: int | None = None,
        *,
        automatic_extractor: bool = False,
    ) -> core.DownloadResultCVM:
        """Execute the download operation inside an existing event loop.

        Mirrors :meth:`execute` but awaits the adapter's async entrypoint
        instead of opening a fresh loop via ``asyncio.run`` — use this when
        composing CVM downloads into already-async code.
        """
        dict_urls_zips, docs_paths = self.__prepare_inputs(
            destination_path, list_docs, initial_year, last_year
        )

        start_time = time.time()

        try:
            tasks = self.__prepare_download_tasks(dict_urls_zips, docs_paths)
            result = await self.__repository.async_download_docs(
                tasks, automatic_extractor=automatic_extractor
            )
            return self.__finalize(result, start_time)

        except Exception as e:
            logger.error(f'Download execution failed: {e}', exc_info=True)
            raise

    def __prepare_inputs(
        self,
        destination_path: str,
        list_docs: list[str] | None,
        initial_year: int | None,
        last_year: int | None,
    ) -> tuple[dict[str, list[str]], dict[str, dict[int, str]]]:
        """Validate years/docs and build the per-doc destination paths.

        Runs the synchronous setup shared by :meth:`execute` and
        :meth:`execute_async`, before any download is dispatched.
        """
        logger.info(
            'Starting download orchestration: path=%s, docs=%s, years=%s-%s',
            destination_path,
            list_docs,
            initial_year,
            last_year,
        )

        range_years = generate_range_years(
            initial_year=initial_year, last_year=last_year
        )

        dict_urls_zips, new_set_docs = generate_urls(
            list_docs=list_docs,
            initial_year=initial_year,
            last_year=last_year,
        )

        verify_paths = VerifyPathsUseCasesCVM(
            destination_path=destination_path,
            new_set_docs=new_set_docs,
            range_years=range_years,
            allowed_unc_roots=self.__allowed_unc_roots,
        )
        docs_paths = verify_paths.execute()

        return dict_urls_zips, docs_paths

    def __finalize(
        self, result: core.DownloadResultCVM, start_time: float
    ) -> core.DownloadResultCVM:
        """Stamp elapsed time on the result and emit completion logs."""
        result.elapsed_time = time.time() - start_time

        logger.info(
            'Download completed in %.2fs: ✓ %d successful, ✗ %d errors',
            result.elapsed_time,
            result.success_count_downloads,
            result.error_count_downloads,
        )

        if result.successful_downloads:
            logger.debug(
                'Successfully downloaded: %s',
                ', '.join(result.successful_downloads),
            )

        if result.failed_downloads:
            failed_info = '; '.join(
                [
                    f'{doc}: {error}'
                    for doc, error in result.failed_downloads.items()
                ]
            )
            logger.warning('Failed downloads: %s', failed_info)

        return result

    def __prepare_download_tasks(
        self,
        dict_zip_to_download: dict[str, list[str]],
        docs_paths: dict[str, dict[int, str]],
    ) -> list[tuple[str, str, str, str]]:
        """Prepare download tasks from URL and path dictionaries."""
        tasks = []
        for doc_name, years_dict in docs_paths.items():
            if doc_name not in dict_zip_to_download:
                raise MissingDownloadUrlError(doc_name)

            url_list = dict_zip_to_download[doc_name]

            url_by_year = {
                str(year): url
                for year in years_dict
                for url in url_list
                if url.endswith(f'{year}.zip')
            }

            for year_int, destination_path in years_dict.items():
                year_str = str(year_int)
                matching_url = url_by_year.get(year_str)

                if matching_url:
                    tasks.append(
                        (matching_url, doc_name, year_str, destination_path)
                    )
                else:
                    logger.warning(
                        'No URL found for %s_%s in dict_zip_to_download',
                        doc_name,
                        year_str,
                    )

        return tasks
