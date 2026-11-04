"""Unit tests for GetAvailableAssetsUseCaseB3."""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.client import (
    GetAvailableAssetsUseCaseB3,
)

pytestmark = pytest.mark.unit

EXPECTED_ASSETS = [
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


class TestGetAvailableAssetsUseCase:
    def test_execute_returns_all_expected_assets(self):
        result = GetAvailableAssetsUseCaseB3.execute()
        assert isinstance(result, list)
        assert len(result) == 9
        for asset in EXPECTED_ASSETS:
            assert asset in result

    def test_execute_returns_only_strings(self):
        result = GetAvailableAssetsUseCaseB3.execute()
        assert all(isinstance(asset, str) for asset in result)

    def test_execute_returns_no_duplicates(self):
        result = GetAvailableAssetsUseCaseB3.execute()
        assert len(result) == len(set(result))

    def test_execute_is_deterministic(self):
        assert GetAvailableAssetsUseCaseB3.execute() == (
            GetAvailableAssetsUseCaseB3.execute()
        )

    @pytest.mark.parametrize('asset', EXPECTED_ASSETS)
    def test_execute_contains_asset(self, asset):
        result = GetAvailableAssetsUseCaseB3.execute()
        assert asset in result
