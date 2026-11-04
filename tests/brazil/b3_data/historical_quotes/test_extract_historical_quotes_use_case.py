from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.client import (
    ExtractHistoricalQuotesUseCaseB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidOutputFilename,
)
from globaldatafinance.brazil.b3_data.historical_quotes.models import (
    DocsToExtractorB3,
)

pytestmark = pytest.mark.unit


class TestExtractHistoricalQuotesUseCaseInitialization:
    def test_initializes_with_dependencies(self):
        use_case = ExtractHistoricalQuotesUseCaseB3()
        assert use_case.zip_reader is not None
        assert use_case.parser is not None

    def test_initializes_zip_reader(self):
        use_case = ExtractHistoricalQuotesUseCaseB3()
        assert hasattr(use_case, 'zip_reader')

    def test_initializes_parser(self):
        use_case = ExtractHistoricalQuotesUseCaseB3()
        assert hasattr(use_case, 'parser')

    def test_does_not_store_a_data_writer(self):
        use_case = ExtractHistoricalQuotesUseCaseB3()
        assert not hasattr(use_case, 'data_writer')


class TestExecuteAsyncMethod:
    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_returns_dict(
        self, mock_assets_service, mock_extraction_service
    ):
        expected_result = {
            'total_files': 1,
            'success_count': 1,
            'error_count': 0,
            'total_records': 100,
            'errors': {},
            'output_file': '/path/output.parquet',
        }
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = expected_result
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {
            '010',
            '020',
        }

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        result = await use_case.execute(docs)
        assert result == expected_result
        mock_assets_service.get_tpmerc_codes_for_assets.assert_called_once_with(
            {'ações'}
        )
        mock_service.extract_from_zip_files.assert_awaited_once_with(
            zip_files={'COTAHIST_A2020.ZIP'},
            target_tpmerc_codes={'010', '020'},
            output_path=Path('/path/to/output/cotahist_extracted.parquet'),
            validated_sources=None,
            all_markets=False,
            requested_years=(2020,),
            missing_years=(),
            asset_classes=['ações'],
            ignored_duplicate_sources=(),
        )

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_constructs_extraction_service(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {
            'total_files': 0,
            'success_count': 0,
            'error_count': 0,
            'total_records': 0,
            'errors': {},
            'output_file': '',
        }
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs, processing_mode='fast')
        mock_extraction_service.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_calls_get_tpmerc_codes(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {}
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {
            '010',
            '020',
        }

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações', 'etf'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs)
        mock_assets_service.get_tpmerc_codes_for_assets.assert_called_once_with(
            {'ações', 'etf'}
        )

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_returns_missing_year_failure(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {
            'total_files': 0,
            'success_count': 0,
            'error_count': 1,
            'total_records': 0,
            'errors': {'coverage': 'Missing requested COTAHIST years: [2020]'},
            'output_file': '',
            'schema_version': 2,
            'integrity': {'status': 'failed', 'missing_years': [2020]},
        }
        mock_extraction_service.return_value = mock_service

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download=set(),
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        result = await use_case.execute(docs)
        assert result['error_count'] == 1
        assert result['integrity']['status'] == 'failed'
        mock_service.extract_from_zip_files.assert_awaited_once()
        assert mock_service.extract_from_zip_files.call_args.kwargs[
            'requested_years'
        ] == (2020,)

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_with_custom_output_filename(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {
            'total_files': 1,
            'success_count': 1,
            'error_count': 0,
            'total_records': 100,
            'errors': {},
            'output_file': '/path/to/output/custom.parquet',
        }
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs, output_filename='custom.parquet')
        call_args = mock_service.extract_from_zip_files.call_args
        assert 'output_path' in call_args.kwargs
        assert (
            call_args.kwargs['output_path']
            == Path('/path/to/output') / 'custom.parquet'
        )

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_with_slow_processing_mode(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {}
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs, processing_mode='slow')
        call_args = mock_extraction_service.call_args
        assert call_args.kwargs['processing_mode'] == 'slow'


class TestExecuteSyncMethod:
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    def test_execute_sync_returns_dict(
        self, mock_assets_service, mock_extraction_service
    ):
        expected_result = {
            'total_files': 1,
            'success_count': 1,
            'error_count': 0,
            'total_records': 100,
            'errors': {},
            'output_file': '/path/output.parquet',
        }
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = expected_result
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        result = use_case.execute_sync(docs)
        assert result == expected_result
        mock_assets_service.get_tpmerc_codes_for_assets.assert_called_once_with(
            {'ações'}
        )
        mock_service.extract_from_zip_files.assert_awaited_once_with(
            zip_files={'COTAHIST_A2020.ZIP'},
            target_tpmerc_codes={'010'},
            output_path=Path('/path/to/output/cotahist_extracted.parquet'),
            validated_sources=None,
            all_markets=False,
            requested_years=(2020,),
            missing_years=(),
            asset_classes=['ações'],
            ignored_duplicate_sources=(),
        )

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    def test_execute_sync_with_all_parameters(
        self, mock_assets_service, mock_extraction_service
    ):
        expected_result = {
            'total_files': 1,
            'success_count': 1,
            'error_count': 0,
            'total_records': 100,
            'errors': {},
            'output_file': '/path/to/output/custom.parquet',
        }
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = expected_result
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        result = use_case.execute_sync(
            docs, processing_mode='slow', output_filename='custom.parquet'
        )
        assert result == expected_result
        mock_assets_service.get_tpmerc_codes_for_assets.assert_called_once_with(
            {'ações'}
        )
        assert (
            mock_extraction_service.call_args.kwargs['processing_mode']
            == 'slow'
        )
        mock_service.extract_from_zip_files.assert_awaited_once_with(
            zip_files={'COTAHIST_A2020.ZIP'},
            target_tpmerc_codes={'010'},
            output_path=Path('/path/to/output') / 'custom.parquet',
            validated_sources=None,
            all_markets=False,
            requested_years=(2020,),
            missing_years=(),
            asset_classes=['ações'],
            ignored_duplicate_sources=(),
        )

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    def test_execute_sync_reports_missing_year_failure(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {
            'total_files': 0,
            'success_count': 0,
            'error_count': 1,
            'total_records': 0,
            'errors': {'coverage': 'Missing requested COTAHIST years: [2020]'},
            'output_file': '',
            'schema_version': 2,
            'integrity': {'status': 'failed', 'missing_years': [2020]},
        }
        mock_extraction_service.return_value = mock_service

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download=set(),
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        result = use_case.execute_sync(docs)
        assert result['error_count'] == 1
        assert result['integrity']['status'] == 'failed'
        mock_extraction_service.assert_called_once()


class TestOutputPathGeneration:
    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_generates_correct_output_path(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {}
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs, output_filename='test.parquet')
        call_args = mock_service.extract_from_zip_files.call_args
        expected_path = Path('/path/to/output') / 'test.parquet'
        assert call_args.kwargs['output_path'] == expected_path

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_uses_default_filename(
        self, mock_assets_service, mock_extraction_service
    ):
        mock_service = AsyncMock()
        mock_service.extract_from_zip_files.return_value = {}
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        docs = DocsToExtractorB3(
            path_of_docs='/path/to/docs',
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path='/path/to/output',
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        await use_case.execute(docs)
        call_args = mock_service.extract_from_zip_files.call_args
        expected_path = Path('/path/to/output') / 'cotahist_extracted.parquet'
        assert call_args.kwargs['output_path'] == expected_path


class TestExecuteRejectsOutputPathTraversal:
    """Regression for finding F1 (security audit).

    The upstream ``validate_output_filename`` is the first defense; this
    suite exercises the second one (``is_relative_to`` check in
    ``client.py``) and proves that even a malicious filename smuggled
    past the upstream validator never reaches the writer and never
    creates a file outside the destination.
    """

    @pytest.mark.asyncio
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.ExtractionServiceB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.AvailableAssetsServiceB3'
    )
    async def test_execute_rejects_traversal_filename_with_poc_value(
        self, mock_assets_service, mock_extraction_service, tmp_path
    ):
        mock_service = AsyncMock()
        mock_extraction_service.return_value = mock_service
        mock_assets_service.get_tpmerc_codes_for_assets.return_value = {'010'}

        destination = tmp_path / 'safe'
        destination.mkdir()
        # PoC value: traversal that, if executed, would write into the
        # parent of tmp_path. We assert: (a) the use case raises and
        # (b) no file appears at the escape target.
        escape_target = tmp_path.parent / 'pwn_extract_use_case_target.parquet'
        assert not escape_target.exists()

        docs = DocsToExtractorB3(
            path_of_docs=str(destination),
            set_assets={'ações'},
            range_years=range(2020, 2021),
            destination_path=str(destination),
            documents_to_download={'COTAHIST_A2020.ZIP'},
        )

        use_case = ExtractHistoricalQuotesUseCaseB3()
        traversal_filename = f'../{escape_target.name}'

        with pytest.raises(InvalidOutputFilename):
            await use_case.execute(docs, output_filename=traversal_filename)

        # Critical: the writer must never have been called and no file
        # must have escaped the destination.
        mock_service.extract_from_zip_files.assert_not_called()
        assert not escape_target.exists()
