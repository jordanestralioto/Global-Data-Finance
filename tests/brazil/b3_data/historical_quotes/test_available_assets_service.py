import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.assets import (
    AvailableAssetsServiceB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    EmptyAssetListError,
    InvalidAssetsName,
)

pytestmark = pytest.mark.unit


class TestGetAvailableAssets:
    def test_returns_list_of_assets(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert isinstance(result, list)

    def test_returns_non_empty_list(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert len(result) > 0

    def test_returns_expected_asset_classes(self):
        expected_assets = [
            'ações',
            'etf',
            'opções',
            'termo',
            'exercicio_opcoes',
            'forward',
            'leilao',
            'lote_bloco',
            'todos',
        ]
        result = AvailableAssetsServiceB3.get_available_assets()
        for asset in expected_assets:
            assert asset in result

    def test_returns_nine_asset_classes(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert len(result) == 9

    def test_all_elements_are_strings(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert all(isinstance(asset, str) for asset in result)

    def test_no_duplicate_assets(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert len(result) == len(set(result))

    def test_is_class_method(self):
        result = AvailableAssetsServiceB3.get_available_assets()
        assert result is not None


class TestValidateAndCreateAssetSet:
    def test_validates_single_valid_asset(self):
        assets_list = ['ações']
        result = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )
        assert isinstance(result, set)
        assert result == {'ações'}

    def test_validates_multiple_valid_assets(self):
        assets_list = ['ações', 'etf', 'opções']
        result = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )
        assert result == {'ações', 'etf', 'opções'}

    def test_validates_all_available_assets(self):
        assets_list = [
            'ações',
            'etf',
            'opções',
            'termo',
            'exercicio_opcoes',
            'forward',
            'leilao',
            'lote_bloco',
            'todos',
        ]
        result = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )
        assert len(result) == 9

    def test_removes_duplicates_from_list(self):
        assets_list = ['ações', 'ações', 'etf', 'etf']
        result = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )
        assert len(result) == 2
        assert result == {'ações', 'etf'}

    def test_raises_empty_asset_list_error_for_empty_list(self):
        assets_list = []
        with pytest.raises(EmptyAssetListError):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_list)

    def test_raises_empty_asset_list_error_for_non_list(self):
        assets_not_list = 'ações'
        with pytest.raises(EmptyAssetListError):
            AvailableAssetsServiceB3.validate_and_create_asset_set(
                assets_not_list
            )

    def test_raises_empty_asset_list_error_for_none(self):
        with pytest.raises(EmptyAssetListError):
            AvailableAssetsServiceB3.validate_and_create_asset_set(None)

    def test_raises_invalid_assets_name_for_non_string_elements(self):
        assets_list = ['ações', 123, 'etf']
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_list)

    def test_raises_invalid_assets_name_for_invalid_asset(self):
        assets_list = ['ações', 'invalid_asset']
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_list)

    def test_raises_invalid_assets_name_for_all_invalid_assets(self):
        assets_list = ['invalid1', 'invalid2']
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_list)

    def test_raises_invalid_assets_name_with_mixed_valid_invalid(self):
        assets_list = ['ações', 'invalid', 'etf']
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_list)

    def test_is_case_insensitive(self):
        assets_list = ['AÇÕES', 'ETF']
        result = AvailableAssetsServiceB3.validate_and_create_asset_set(
            assets_list
        )
        assert result == {'ações', 'etf'}

    def test_validates_with_dict_input(self):
        assets_dict = {'ações': True}
        with pytest.raises(EmptyAssetListError):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_dict)

    def test_validates_with_set_input(self):
        assets_set = {'ações', 'etf'}
        with pytest.raises(EmptyAssetListError):
            AvailableAssetsServiceB3.validate_and_create_asset_set(assets_set)


class TestGetTpmercCodesForAssets:
    def test_returns_codes_for_acoes(self):
        asset_set = {'ações'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert isinstance(result, set)
        assert result == {'010', '020'}

    def test_returns_codes_for_etf(self):
        asset_set = {'etf'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'010', '020'}

    def test_returns_codes_for_opcoes(self):
        asset_set = {'opções'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'070', '080'}

    def test_returns_codes_for_termo(self):
        asset_set = {'termo'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'030'}

    def test_returns_codes_for_exercicio_opcoes(self):
        asset_set = {'exercicio_opcoes'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'012', '013'}

    def test_returns_codes_for_forward(self):
        asset_set = {'forward'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'050', '060'}

    def test_returns_codes_for_leilao(self):
        asset_set = {'leilao'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'017'}

    def test_returns_combined_codes_for_multiple_assets(self):
        asset_set = {'ações', 'opções'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'010', '020', '070', '080'}

    def test_returns_all_codes_for_all_assets(self):
        asset_set = {
            'ações',
            'etf',
            'opções',
            'termo',
            'exercicio_opcoes',
            'forward',
            'leilao',
        }
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        expected_codes = {
            '010',
            '020',
            '030',
            '050',
            '060',
            '070',
            '080',
            '012',
            '013',
            '017',
        }
        assert result == expected_codes

    def test_returns_empty_set_for_empty_input(self):
        asset_set = set()
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == set()

    def test_invalid_assets_are_rejected_before_mapping(self):
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(
                ['ações', 'invalid_asset']
            )

    def test_all_invalid_assets_are_rejected_before_mapping(self):
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(
                ['invalid1', 'invalid2']
            )

    def test_handles_uppercase_assets_normalized(self):
        asset_set = AvailableAssetsServiceB3.validate_and_create_asset_set(
            ['AÇÕES']
        )
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert result == {'010', '020'}

    def test_rejects_whitespace_wrapped_asset_names_before_mapping(self):
        with pytest.raises(InvalidAssetsName):
            AvailableAssetsServiceB3.validate_and_create_asset_set(
                [' ações ', '  etf  ']
            )

    def test_no_duplicate_codes_returned(self):
        asset_set = {'ações', 'etf'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert len(result) == 2
        assert result == {'010', '020'}

    def test_all_codes_are_strings(self):
        asset_set = {'ações', 'opções', 'termo'}
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert all(isinstance(code, str) for code in result)

    def test_all_codes_are_three_digits(self):
        asset_set = {
            'ações',
            'etf',
            'opções',
            'termo',
            'exercicio_opcoes',
            'forward',
            'leilao',
        }
        result = AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            asset_set
        )
        assert all(len(code) == 3 for code in result)
        assert all(code.isdigit() for code in result)
