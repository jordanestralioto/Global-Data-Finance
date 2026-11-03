"""Company document catalog, period validation, and download orchestration."""

from .client import (
    DownloadDocumentsUseCaseCVM,
    VerifyPathsUseCasesCVM,
    generate_range_years,
    generate_urls,
    get_available_docs,
    get_available_years,
)
from .core import (
    AvailableYearsCVM,
    AvailableYearsInfoCVM,
    DictZipsToDownloadCVM,
)
from .errors import (
    EmptyDocumentListError,
    InvalidDocumentName,
    InvalidDocumentType,
    InvalidFirstYear,
    InvalidLastYear,
    MissingDownloadUrlError,
)

__all__ = [
    # core (domain)
    'AvailableYearsCVM',
    'AvailableYearsInfoCVM',
    'DictZipsToDownloadCVM',
    # client (use cases)
    'DownloadDocumentsUseCaseCVM',
    'EmptyDocumentListError',
    'InvalidDocumentName',
    'InvalidDocumentType',
    # errors
    'InvalidFirstYear',
    'InvalidLastYear',
    'MissingDownloadUrlError',
    'VerifyPathsUseCasesCVM',
    'generate_range_years',
    'generate_urls',
    'get_available_docs',
    'get_available_years',
]
