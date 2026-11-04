"""Exceptions for CVM fundamental_stocks_data module.

Contains all specific domain and validation exception types raised
during CVM regulatory data processing, filtering, and extraction.
"""


class CvmError(Exception):
    """Base exception for all CVM feature exceptions."""


class InvalidFirstYear(CvmError):
    """Indicate that the first requested year is outside the valid range."""

    def __init__(self, minimal_first_year: int, current_year: int):
        """Create an error describing the accepted first-year bounds."""
        super().__init__(
            f'Invalid first year. You must provide an integer value greater '
            f'than or equal to {minimal_first_year} and less than or equal to '
            f'{current_year}.'
        )


class InvalidLastYear(CvmError):
    """Indicate that the last requested year is outside the valid range."""

    def __init__(self, first_year: int, current_year: int):
        """Create an error describing the accepted last-year bounds."""
        super().__init__(
            f'Invalid last year. You must provide an integer value greater '
            f'than or equal to {first_year} and less than or equal to '
            f'{current_year}.'
        )


class InvalidDocumentName(CvmError):
    """Indicate that a requested document name is not supported."""

    def __init__(self, doc_name: str, list_available_docs: list):
        """Create an error listing the available document names."""
        super().__init__(
            f'Invalid document name: {doc_name}. The document name must be a '
            f'string and one of the following: {list_available_docs}.'
        )


class InvalidDocumentType(CvmError):
    """Indicate that a document name has the wrong input type."""

    def __init__(self, doc_name: str):
        """Create an error for the invalid document value."""
        super().__init__(
            f'Invalid document type: {doc_name}. The document name must be a '
            'string.'
        )


class EmptyDocumentListError(CvmError):
    """Indicate that no document types were selected for download."""

    def __init__(self, message: str = 'The document list cannot be empty.'):
        """Create an error with an optional replacement message."""
        super().__init__(message)


class MissingDownloadUrlError(CvmError):
    """Indicate that a selected document has no download URL."""

    def __init__(self, doc_name: str):
        """Create an error for the document without a download URL."""
        super().__init__(
            f'No download URL was found for the document: {doc_name}'
        )
