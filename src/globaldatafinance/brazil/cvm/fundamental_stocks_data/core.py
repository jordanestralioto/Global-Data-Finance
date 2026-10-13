"""Core domain for CVM fundamental_stocks_data.

Consolidates the prior `domain/` layer (available docs/years, URL builder,
download result) into a single module per the flat per-source layout.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import NamedTuple

from .errors import (
    InvalidDocumentName,
    InvalidDocumentType,
    InvalidFirstYear,
    InvalidLastYear,
)

DOCUMENT_START_YEARS: dict[str, int] = {
    'CGVN': 2018,
    'FRE': 2010,
    'FCA': 2010,
    'DFP': 2010,
    'ITR': 2011,
    'IPE': 2003,
    'VLMO': 2018,
}


class AvailableYearsInfoCVM(NamedTuple):
    """Type-safe container for CVM document year ranges.

    Provides attribute access for year information instead of
    ``dict[str, int]`` with magic string keys.

    Example:
        >>> years = AvailableYearsInfoCVM(
        ...     general_min_year=2010,
        ...     itr_min_year=2011,
        ...     cgvn_vlmo_min_year=2018,
        ...     current_year=2026,
        ... )
        >>> years.general_min_year
        2010
        >>> years.current_year
        2026
        >>> years._asdict()  # escape hatch for dict consumers
        {'general_min_year': 2010, ...}
    """

    general_min_year: int
    itr_min_year: int
    cgvn_vlmo_min_year: int
    current_year: int

    @property
    def ipe_min_year(self) -> int:
        """Return the official IPE minimum without changing tuple fields."""
        return DOCUMENT_START_YEARS['IPE']


_DICT_AVAILABLE_DOCS: dict[str, str] = {
    'CGVN': (
        '(Governance Code Report) a periodic document that records '
        'information '
        'about adherence/compatibility with the Corporate Governance Code for '
        'publicly traded companies — governance structure, committees, '
        'policies, and relevant indicators.'
    ),
    'FRE': (
        '(Reference Form) an electronic document (periodic/eventual) that '
        'gathers corporate and descriptive information required by the CVM: '
        'activities, risk factors, corporate and capital structure, '
        'management, '
        'compensation policies, information about securities, auditing, and '
        'other regulatory disclosures.'
    ),
    'FCA': (
        '(Registration Form) an electronic form (periodic/eventual) with the '
        "company's official registration data and its updates: identification "
        '(CNPJ, corporate name), address, registration status, segment, '
        'identifier codes, and registration/contact information.'
    ),
    'DFP': (
        '(Standardized Financial Statements) a periodic electronic form '
        '(related to the closed fiscal year) containing the standardized '
        'financial statements required by the CVM: Balance Sheet (BPA/BPP), '
        'Income Statement (DRE), Cash Flow Statement (DFC — direct/indirect '
        'methods, as applicable), Statement of Value Added (DVA), explanatory '
        "notes, independent auditor's report, and standardized annexes."
    ),
    'ITR': (
        '(Quarterly Information) a periodic electronic form with the '
        'statements and disclosures for each quarter — BPA/BPP, DRE, DFC '
        '(when applicable), and quarterly notes/disclosures required by the '
        'applicable regulation.'
    ),
    'IPE': (
        '(Periodic and Eventual Documents) a set of unstructured documents '
        '(minutes, material facts, announcements, reports, prospectuses, '
        'official letters, etc.) made available with metadata and a '
        'link/file; '
        'the format and content vary depending on the document type.'
    ),
    'VLMO': (
        '(Data on Negotiated and Held Securities) periodic reports on '
        'securities '
        'linked to the company (trades, quantities, positions, custody, and '
        'related information) provided as datasets on the CVM Open Data '
        'Portal.'
    ),
}


def get_available_docs() -> dict[str, str]:
    """Get a dictionary of all available CVM document types."""
    return _DICT_AVAILABLE_DOCS.copy()


def validate_docs_name(docs_name: str) -> None:
    """Validate that a document name is valid and of the correct type."""
    if not isinstance(docs_name, str):
        raise InvalidDocumentType(docs_name)

    key = docs_name.strip().upper()
    if key not in _DICT_AVAILABLE_DOCS:
        raise InvalidDocumentName(docs_name, list(_DICT_AVAILABLE_DOCS))


def _build_url_prefix(doc: str) -> str:
    """Build the CVM ZIP prefix for a registered document code."""
    return (
        'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/'
        f'{doc}/DADOS/{doc.lower()}_cia_aberta_'
    )


_DICT_URL_DOCS: dict[str, str] = {
    doc: _build_url_prefix(doc) for doc in _DICT_AVAILABLE_DOCS
}


def get_url_docs(
    list_docs: list[str] | None = None,
) -> tuple[dict[str, str], set[str]]:
    """Get URLs for specified docs or all docs when the list is empty."""
    if list_docs is not None and not isinstance(list_docs, list):
        raise TypeError('list_docs must be a list of strings or None')

    dict_urls: dict[str, str] = {}
    set_docs: set[str] = set()

    if not list_docs:
        dict_urls = _DICT_URL_DOCS.copy()
        set_docs.update(_DICT_URL_DOCS.keys())
        return dict_urls, set_docs

    for doc in list_docs:
        validate_docs_name(doc)

        doc_key = doc.strip().upper()
        if doc_key not in _DICT_URL_DOCS:
            raise ValueError(f"No URL available for doc '{doc}'")

        if doc_key not in set_docs:
            dict_urls[doc_key] = _DICT_URL_DOCS[doc_key]
            set_docs.add(doc_key)

    return dict_urls, set_docs


class AvailableYearsCVM:
    """Provides minimum allowed years and helpers for CVM documents."""

    def get_current_year(self) -> int:
        """Return current year (system date)."""
        return date.today().year

    def get_minimal_general_year(self) -> int:
        """Return minimum supported year for general documents."""
        return DOCUMENT_START_YEARS['DFP']

    def get_minimal_itr_year(self) -> int:
        """Return minimum supported year for ITR documents."""
        return DOCUMENT_START_YEARS['ITR']

    def get_minimal_cgvn_vlmo_year(self) -> int:
        """Return minimum supported year for CGVN/VLMO documents."""
        return DOCUMENT_START_YEARS['CGVN']

    def get_minimal_ipe_year(self) -> int:
        """Return the earliest official IPE metadata archive year."""
        return DOCUMENT_START_YEARS['IPE']

    def __validate_years(self, initial_year: int, last_year: int) -> None:
        if (
            not isinstance(initial_year, int)
            or initial_year < self.get_minimal_ipe_year()
            or initial_year > self.get_current_year()
        ):
            raise InvalidFirstYear(
                self.get_minimal_ipe_year(), self.get_current_year()
            )

        if (
            not isinstance(last_year, int)
            or last_year > self.get_current_year()
            or initial_year > last_year
        ):
            raise InvalidLastYear(initial_year, self.get_current_year())

    def return_range_years(
        self,
        initial_year: int | None = None,
        last_year: int | None = None,
    ) -> range:
        """Return inclusive year range; defaults span all supported years."""
        if initial_year is None:
            initial_year = self.get_minimal_general_year()
        if last_year is None:
            last_year = self.get_current_year()

        self.__validate_years(initial_year, last_year)

        return range(initial_year, last_year + 1)


class DictZipsToDownloadCVM:
    """Builds the per-doc ZIP-URL map for the requested year range."""

    def __init__(self) -> None:
        """Initialize the helper used to validate requested years."""
        self._available_years = AvailableYearsCVM()

    def get_dict_zips_to_download(
        self,
        list_docs: list[str] | None = None,
        initial_year: int | None = None,
        last_year: int | None = None,
    ) -> tuple[dict[str, list[str]], set[str]]:
        """Build a `{doc_code: [zip_url_per_year]}` map plus the doc set."""
        dict_urls_docs, set_docs = get_url_docs(list_docs)

        if initial_year is None:
            initial_year = min(DOCUMENT_START_YEARS[doc] for doc in set_docs)
        range_years: range = self._available_years.return_range_years(
            initial_year, last_year
        )

        dict_zips_to_download: dict[str, list[str]] = {
            doc: [
                url + str(year) + '.zip'
                for year in range_years
                if year >= DOCUMENT_START_YEARS[doc]
            ]
            for doc, url in dict_urls_docs.items()
        }

        return dict_zips_to_download, set_docs


@dataclass
class DownloadResultCVM:
    """Aggregated result of a CVM download run."""

    successful_downloads: list[str] = field(default_factory=list)
    failed_downloads: dict[str, str] = field(default_factory=dict)
    elapsed_time: float = 0.0
    _success_set: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        """Build the private set used to deduplicate successful downloads."""
        self._success_set = set(self.successful_downloads)

    @property
    def success_count_downloads(self) -> int:
        """Return the number of successful downloads."""
        return len(self.successful_downloads)

    @property
    def error_count_downloads(self) -> int:
        """Return the number of failed downloads."""
        return len(self.failed_downloads)

    def has_errors(self) -> bool:
        """Return ``True`` when at least one download failed."""
        return self.error_count_downloads > 0

    def add_success_downloads(self, item: str) -> None:
        """Record a successful download once."""
        if item not in self._success_set:
            self.successful_downloads.append(item)
            self._success_set.add(item)

    def add_error_downloads(self, item: str, error: str) -> None:
        """Record the error associated with a failed download."""
        self.failed_downloads[item] = error

    def __str__(self) -> str:
        """Return a concise summary of the download result."""
        return (
            f'DownloadResultCVM(success={self.success_count_downloads}, '
            f'errors={self.error_count_downloads})'
        )
