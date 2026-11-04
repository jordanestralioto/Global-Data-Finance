"""Type-validation error paths for the flat B3 layout.

Covers the TypeError + invalid-argument branches that were previously
exercised across multiple files in the layered structure but slipped through
the consolidation. Each test pins one specific raise-site to keep coverage
parity with the pre-refactor baseline (R5 mitigation).
"""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.client import (
    CreateDocsToExtractUseCaseB3,
    CreateSetToDownloadUseCaseB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidOutputFilename,
    InvalidProcessingMode,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ExtractionConfigServiceB3,
)
from globaldatafinance.macro_exceptions import InvalidDestinationPathError

pytestmark = pytest.mark.unit


class TestCreateSetToDownloadUseCaseB3TypeErrors:
    def test_non_string_path_raises_type_error(self):
        with pytest.raises(TypeError, match='path_of_docs must be a string'):
            CreateSetToDownloadUseCaseB3.execute(range(2020, 2021), 123)  # type: ignore[arg-type]

    def test_empty_path_raises_invalid_destination(self):
        with pytest.raises(InvalidDestinationPathError):
            CreateSetToDownloadUseCaseB3.execute(range(2020, 2021), '   ')


class TestCreateDocsToExtractUseCaseB3TypeErrors:
    def test_non_string_path_of_docs_raises(self):
        with pytest.raises(TypeError, match='path_of_docs must be a string'):
            CreateDocsToExtractUseCaseB3(
                path_of_docs=42,  # type: ignore[arg-type]
                assets_list=['ações'],
                initial_year=2020,
                last_year=2021,
            )

    def test_non_string_destination_path_raises(self):
        with pytest.raises(
            TypeError, match='destination_path must be a string'
        ):
            CreateDocsToExtractUseCaseB3(
                path_of_docs='test-data',
                assets_list=['ações'],
                initial_year=2020,
                last_year=2021,
                destination_path=42,  # type: ignore[arg-type]
            )


class TestExtractionConfigServiceTypeErrors:
    def test_validate_processing_mode_non_string_raises(self):
        with pytest.raises(
            TypeError, match='processing_mode must be a string'
        ):
            ExtractionConfigServiceB3.validate_processing_mode(42)  # type: ignore[arg-type]

    def test_validate_processing_mode_invalid_raises(self):
        with pytest.raises(InvalidProcessingMode):
            ExtractionConfigServiceB3.validate_processing_mode('not-a-mode')

    def test_validate_output_filename_non_string_raises(self):
        with pytest.raises(
            TypeError, match='output_filename must be a string'
        ):
            ExtractionConfigServiceB3.validate_output_filename(42)  # type: ignore[arg-type]

    def test_validate_output_filename_empty_raises(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename('   ')


class TestInvalidOutputFilename:
    def test_message_prefixed(self):
        with pytest.raises(InvalidOutputFilename, match='Invalid output'):
            raise InvalidOutputFilename('bad name')
