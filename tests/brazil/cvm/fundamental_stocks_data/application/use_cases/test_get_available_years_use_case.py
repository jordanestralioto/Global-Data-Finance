from unittest.mock import patch

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AvailableYearsInfoCVM,
    get_available_years,
)


@pytest.mark.unit
class TestGetAvailableYearsUseCase:
    def test_execute_returns_named_tuple(self):
        use_case = get_available_years
        result = use_case()

        assert isinstance(result, AvailableYearsInfoCVM)

    def test_execute_has_all_fields(self):
        use_case = get_available_years
        result = use_case()

        assert hasattr(result, 'general_min_year')
        assert hasattr(result, 'itr_min_year')
        assert hasattr(result, 'cgvn_vlmo_min_year')
        assert hasattr(result, 'current_year')

    def test_execute_all_values_are_integers(self):
        use_case = get_available_years
        result = use_case()

        assert isinstance(result.general_min_year, int)
        assert isinstance(result.itr_min_year, int)
        assert isinstance(result.cgvn_vlmo_min_year, int)
        assert isinstance(result.current_year, int)

    def test_minimum_years_are_reasonable(self):
        use_case = get_available_years
        result = use_case()

        assert result.general_min_year < result.current_year
        assert result.itr_min_year < result.current_year
        assert result.cgvn_vlmo_min_year < result.current_year

    def test_current_year_is_reasonable(self):
        use_case = get_available_years
        result = use_case()

        from datetime import datetime

        current_year = datetime.now().year

        assert abs(result.current_year - current_year) <= 1

    def test_execute_propagates_underlying_failure(self):
        use_case = get_available_years
        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.AvailableYearsCVM.get_minimal_general_year',
                side_effect=RuntimeError('boom'),
            ),
            pytest.raises(RuntimeError, match='boom'),
        ):
            use_case()

    def test_result_is_iterable_like_tuple(self):
        use_case = get_available_years
        result = use_case()

        values = list(result)
        assert len(values) == 4
        assert all(isinstance(v, int) for v in values)

    def test_asdict_returns_dict(self):
        use_case = get_available_years
        result = use_case()

        d = result._asdict()
        assert isinstance(d, dict)
        assert set(d.keys()) == {
            'general_min_year',
            'itr_min_year',
            'cgvn_vlmo_min_year',
            'current_year',
        }
