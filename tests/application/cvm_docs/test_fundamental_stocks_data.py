from unittest.mock import Mock, patch

import pytest

from globaldatafinance.application import FundamentalStocksDataCVM
from globaldatafinance.application.cvm_docs import (
    fundamental_stocks_data as facade_module,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AvailableYearsInfoCVM,
)
from globaldatafinance.core.config import NetworkSettings, Settings

pytestmark = pytest.mark.unit


class TestFundamentalStocksData:
    def test_initialization(self):
        cvm = FundamentalStocksDataCVM()
        assert cvm is not None
        assert repr(cvm) == 'FundamentalStocksDataCVM()'

    def test_initialization_sets_download_adapter(self):
        cvm = FundamentalStocksDataCVM()
        assert cvm.download_adapter is not None
        assert hasattr(cvm.download_adapter, 'automatic_extractor')

    def test_initialization_propagates_network_settings(self):
        controlled_network = NetworkSettings(
            timeout=321,
            max_retries=4,
            retry_backoff=1.7,
            user_agent='controlled-client/1.0',
        )
        custom_settings = Settings(network=controlled_network)

        cvm = FundamentalStocksDataCVM(settings=custom_settings)
        adapter = cvm.download_adapter

        assert cvm.settings == custom_settings
        assert adapter.requests_adapter.timeout == 321
        assert adapter.max_retries == 4
        assert adapter.retry_strategy.multiplier == 1.7
        assert adapter.retry_strategy.initial_backoff == 1.0
        assert adapter.retry_strategy.max_backoff == 120.0
        assert adapter.requests_adapter.default_headers == {
            'User-Agent': 'controlled-client/1.0'
        }

    def test_get_available_docs(self):
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()
        assert isinstance(docs, dict)
        assert len(docs) > 0
        assert 'DFP' in docs or 'ITR' in docs

    def test_get_available_years(self):
        cvm = FundamentalStocksDataCVM()
        years = cvm.get_available_years()
        assert isinstance(years, AvailableYearsInfoCVM)
        assert hasattr(years, 'general_min_year')

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_all_parameters(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 5
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = ['DFP_2023.zip']
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(
            destination_path='/data/cvm',
            list_docs=['DFP', 'ITR'],
            initial_year=2020,
            last_year=2023,
            automatic_extractor=True,
        )

        mock_download_instance.execute.assert_called_once()
        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['destination_path'] == '/data/cvm'
        assert call_args[1]['list_docs'] == ['DFP', 'ITR']
        assert call_args[1]['initial_year'] == 2020
        assert call_args[1]['last_year'] == 2023

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_minimal_parameters(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 3
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = ['DFP_2023.zip']
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(destination_path='/data/cvm')

        mock_download_instance.execute.assert_called_once()

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_enables_automatic_extractor_when_true(
        self, mock_download_use_case
    ):
        mock_result = Mock()
        mock_result.success_count_downloads = 2
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()

        cvm.download(destination_path='/data/cvm', automatic_extractor=True)
        mock_download_instance.execute.assert_called_once()
        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['automatic_extractor'] is True

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_specific_docs(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 2
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = ['DFP_2023.zip', 'DFP_2022.zip']
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(destination_path='/data/cvm', list_docs=['DFP'])

        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['list_docs'] == ['DFP']

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_year_range(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 4
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(
            destination_path='/data/cvm', initial_year=2020, last_year=2023
        )

        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['initial_year'] == 2020
        assert call_args[1]['last_year'] == 2023

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_errors(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 2
        mock_result.error_count_downloads = 1
        mock_result.successful_downloads = ['DFP_2023.zip', 'DFP_2022.zip']
        mock_result.failed_downloads = {'ITR_2023.zip': 'Network error'}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(destination_path='/data/cvm', list_docs=['DFP', 'ITR'])

        assert mock_result.error_count_downloads == 1

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_without_automatic_extractor(
        self, mock_download_use_case
    ):
        mock_result = Mock()
        mock_result.success_count_downloads = 3
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(destination_path='/data/cvm', automatic_extractor=False)

        mock_download_instance.execute.assert_called_once()

    def test_repr_returns_correct_string(self):
        cvm = FundamentalStocksDataCVM()
        assert repr(cvm) == 'FundamentalStocksDataCVM()'

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_calls_result_formatter(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 1
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = ['DFP_2023.zip']
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        with patch.object(
            facade_module, 'DownloadResultFormatter'
        ) as mock_formatter:
            cvm = FundamentalStocksDataCVM()
            cvm.download(destination_path='/data/cvm')

        mock_formatter.return_value.print_result.assert_called_once_with(
            mock_result
        )

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_none_list_docs(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 5
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(destination_path='/data/cvm', list_docs=None)

        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['list_docs'] is None

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_with_none_years(self, mock_download_use_case):
        mock_result = Mock()
        mock_result.success_count_downloads = 3
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        cvm.download(
            destination_path='/data/cvm', initial_year=None, last_year=None
        )

        call_args = mock_download_instance.execute.call_args
        assert call_args[1]['initial_year'] is None
        assert call_args[1]['last_year'] is None

    def test_get_available_docs_returns_dict(self):
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()
        assert isinstance(docs, dict)

    def test_get_available_years_returns_named_tuple(self):
        cvm = FundamentalStocksDataCVM()
        years = cvm.get_available_years()
        assert isinstance(years, AvailableYearsInfoCVM)

    def test_initialization_creates_use_cases(self):
        with (
            patch.object(
                facade_module, 'DownloadDocumentsUseCaseCVM'
            ) as mock_download_use_case,
            patch.object(
                facade_module, 'DownloadResultFormatter'
            ) as mock_formatter,
        ):
            cvm = FundamentalStocksDataCVM()

        mock_download_use_case.assert_called_once_with(
            cvm.download_adapter, allowed_unc_roots=()
        )
        mock_formatter.assert_called_once_with(use_colors=True)

    @patch(
        'globaldatafinance.application.cvm_docs.fundamental_stocks_data.DownloadDocumentsUseCaseCVM'
    )
    def test_download_returns_download_result(self, mock_download_use_case):
        """Test that download() returns a DownloadResultCVM object."""
        mock_result = Mock()
        mock_result.success_count_downloads = 1
        mock_result.error_count_downloads = 0
        mock_result.successful_downloads = []
        mock_result.failed_downloads = {}
        mock_result.elapsed_time = 1.5
        mock_download_instance = Mock()
        mock_download_instance.execute.return_value = mock_result
        mock_download_use_case.return_value = mock_download_instance

        cvm = FundamentalStocksDataCVM()
        result = cvm.download(destination_path='/data/cvm')
        assert result is not None
        assert result == mock_result
