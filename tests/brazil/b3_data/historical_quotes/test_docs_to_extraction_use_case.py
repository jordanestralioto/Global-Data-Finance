from unittest.mock import MagicMock, patch

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.client import (
    CreateDocsToExtractUseCaseB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    EmptyAssetListError,
    InvalidAssetsName,
    InvalidFirstYear,
    InvalidLastYear,
)
from globaldatafinance.brazil.b3_data.historical_quotes.models import (
    DocsToExtractorB3,
)

pytestmark = pytest.mark.unit


class TestCreateDocsToExtractUseCaseInitialization:
    def test_initializes_with_all_parameters(self):
        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações', 'etf'],
            initial_year=2020,
            last_year=2024,
            destination_path='/path/to/output',
        )
        assert use_case.path_of_docs == '/path/to/docs'
        assert use_case.assets_list == ['ações', 'etf']
        assert use_case.initial_year == 2020
        assert use_case.last_year == 2024
        assert use_case.destination_path == '/path/to/output'

    def test_initializes_without_destination_path(self):
        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
        )
        assert use_case.destination_path == '/path/to/docs'

    def test_initializes_with_none_destination_path(self):
        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
            destination_path=None,
        )
        assert use_case.destination_path == '/path/to/docs'

    def test_stores_all_parameters_correctly(self):
        path = '/test/path'
        assets = ['ações', 'etf', 'opções']
        initial = 2015
        last = 2020
        dest = '/test/output'
        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs=path,
            assets_list=assets,
            initial_year=initial,
            last_year=last,
            destination_path=dest,
        )
        assert use_case.path_of_docs == path
        assert use_case.assets_list == assets
        assert use_case.initial_year == initial
        assert use_case.last_year == last
        assert use_case.destination_path == dest


class TestCreateDocsToExtractUseCaseExecute:
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_returns_docs_to_extractor(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações', 'etf'}
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = {'COTAHIST_A2020.ZIP'}

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações', 'etf'],
            initial_year=2020,
            last_year=2024,
            destination_path='/path/to/output',
        )
        result = use_case.execute()
        assert isinstance(result, DocsToExtractorB3)

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_calls_set_assets_use_case(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = set()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
        )
        use_case.execute()
        mock_set_assets.execute.assert_called_once_with(['ações'])

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_calls_range_years_use_case(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = set()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
        )
        use_case.execute()
        mock_range_years.execute.assert_called_once_with(2020, 2024)

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_calls_verify_destination_path_use_case(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_instance = MagicMock()
        mock_verify_path.return_value = mock_verify_instance
        mock_set_download.execute.return_value = set()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
            destination_path='/output',
        )
        use_case.execute()
        mock_verify_instance.execute.assert_called_once_with(
            '/output', allowed_unc_roots=()
        )

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_calls_set_to_download_use_case(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações'}
        year_range = range(2020, 2025)
        mock_range_years.execute.return_value = year_range
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = set()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2024,
        )
        use_case.execute()
        mock_set_download.execute.assert_called_once_with(
            year_range, '/path/to/docs', allowed_unc_roots=()
        )

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_builds_entity_with_correct_data(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações', 'etf'}
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = {
            'COTAHIST_A2020.ZIP',
            'COTAHIST_A2021.ZIP',
        }

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações', 'etf'],
            initial_year=2020,
            last_year=2024,
            destination_path='/output',
        )
        result = use_case.execute()
        assert result.path_of_docs == '/path/to/docs'
        assert result.set_assets == {'ações', 'etf'}
        assert result.range_years == range(2020, 2025)
        assert result.destination_path == '/output'
        assert result.documents_to_download == {
            'COTAHIST_A2020.ZIP',
            'COTAHIST_A2021.ZIP',
        }

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    def test_execute_raises_empty_asset_list_error(self, mock_set_assets):
        mock_set_assets.execute.side_effect = EmptyAssetListError()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=[],
            initial_year=2020,
            last_year=2024,
        )
        with pytest.raises(EmptyAssetListError):
            use_case.execute()

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    def test_execute_raises_invalid_assets_name(self, mock_set_assets):
        mock_set_assets.execute.side_effect = InvalidAssetsName(
            ['invalid'], ['ações', 'etf']
        )

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['invalid'],
            initial_year=2020,
            last_year=2024,
        )
        with pytest.raises(InvalidAssetsName):
            use_case.execute()

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    def test_execute_raises_invalid_first_year(
        self, mock_range_years, mock_set_assets
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.side_effect = InvalidFirstYear(1986, 2024)

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=1900,
            last_year=2024,
        )
        with pytest.raises(InvalidFirstYear):
            use_case.execute()

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    def test_execute_raises_invalid_last_year(
        self, mock_range_years, mock_set_assets
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.side_effect = InvalidLastYear(2020, 2024)

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2030,
        )
        with pytest.raises(InvalidLastYear):
            use_case.execute()

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_with_single_asset(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        mock_set_assets.execute.return_value = {'ações'}
        mock_range_years.execute.return_value = range(2020, 2021)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = {'COTAHIST_A2020.ZIP'}

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=['ações'],
            initial_year=2020,
            last_year=2020,
        )
        result = use_case.execute()
        assert len(result.set_assets) == 1
        assert 'ações' in result.set_assets

    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetAssetsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateRangeYearsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.VerifyDestinationPathsUseCaseB3'
    )
    @patch(
        'globaldatafinance.brazil.b3_data.historical_quotes.client.CreateSetToDownloadUseCaseB3'
    )
    def test_execute_with_all_assets(
        self,
        mock_set_download,
        mock_verify_path,
        mock_range_years,
        mock_set_assets,
    ):
        all_assets = {
            'ações',
            'etf',
            'opções',
            'termo',
            'exercicio_opcoes',
            'forward',
            'leilao',
        }
        mock_set_assets.execute.return_value = all_assets
        mock_range_years.execute.return_value = range(2020, 2025)
        mock_verify_path.return_value.execute.return_value = None
        mock_set_download.execute.return_value = set()

        use_case = CreateDocsToExtractUseCaseB3(
            path_of_docs='/path/to/docs',
            assets_list=list(all_assets),
            initial_year=2020,
            last_year=2024,
        )
        result = use_case.execute()
        assert len(result.set_assets) == 7
