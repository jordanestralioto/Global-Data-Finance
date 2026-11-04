from datetime import date
from unittest.mock import Mock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AvailableYearsCVM,
    InvalidFirstYear,
    InvalidLastYear,
    core,
)


@pytest.mark.unit
class TestAvailableYears:
    @pytest.fixture
    def available_years(self):
        return AvailableYearsCVM()

    def test_get_current_year_returns_current_year(self, available_years):
        current_year = available_years.get_current_year()
        expected_year = date.today().year

        assert current_year == expected_year

    def test_get_current_year_returns_integer(self, available_years):
        current_year = available_years.get_current_year()
        assert isinstance(current_year, int)

    def test_get_minimal_geral_year_returns_2010(self, available_years):
        minimal_year = available_years.get_minimal_general_year()
        assert minimal_year == 2010

    def test_get_minimal_geral_year_returns_integer(self, available_years):
        minimal_year = available_years.get_minimal_general_year()
        assert isinstance(minimal_year, int)

    def test_get_minimal_itr_year_returns_2011(self, available_years):
        minimal_itr_year = available_years.get_minimal_itr_year()
        assert minimal_itr_year == 2011

    def test_get_minimal_itr_year_returns_integer(self, available_years):
        minimal_itr_year = available_years.get_minimal_itr_year()
        assert isinstance(minimal_itr_year, int)

    def test_get_minimal_cgvn_vlmo_year_returns_2018(self, available_years):
        minimal_cgvn_vlmo_year = available_years.get_minimal_cgvn_vlmo_year()
        assert minimal_cgvn_vlmo_year == 2018

    def test_get_minimal_cgvn_vlmo_year_returns_integer(self, available_years):
        minimal_cgvn_vlmo_year = available_years.get_minimal_cgvn_vlmo_year()
        assert isinstance(minimal_cgvn_vlmo_year, int)

    def test_return_range_years_with_default_parameters(self, available_years):
        years_range = available_years.return_range_years()

        assert isinstance(years_range, range)
        assert years_range.start == 2010
        assert years_range.stop == date.today().year + 1

    def test_return_range_years_with_custom_range(self, available_years):
        years_range = available_years.return_range_years(2015, 2020)

        assert isinstance(years_range, range)
        assert years_range.start == 2015
        assert years_range.stop == 2021
        assert list(years_range) == [2015, 2016, 2017, 2018, 2019, 2020]

    def test_return_range_years_single_year(self, available_years):
        years_range = available_years.return_range_years(2020, 2020)

        assert list(years_range) == [2020]

    def test_return_range_years_with_only_initial_year(self, available_years):
        years_range = available_years.return_range_years(initial_year=2015)

        assert years_range.start == 2015
        assert years_range.stop == date.today().year + 1

    def test_return_range_years_with_only_last_year(self, available_years):
        years_range = available_years.return_range_years(last_year=2020)

        assert years_range.start == 2010
        assert years_range.stop == 2021

    def test_return_range_years_includes_both_boundaries(
        self, available_years
    ):
        years_range = available_years.return_range_years(2018, 2022)
        years_list = list(years_range)

        assert 2018 in years_list
        assert 2022 in years_list
        assert len(years_list) == 5

    def test_return_range_years_with_initial_year_below_minimum_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidFirstYear):
            available_years.return_range_years(2002, 2020)

    def test_return_range_years_with_initial_year_above_current_raises_error(
        self, available_years
    ):
        future_year = date.today().year + 1
        with pytest.raises(InvalidFirstYear):
            available_years.return_range_years(future_year, future_year)

    def test_return_range_years_with_last_year_above_current_raises_error(
        self, available_years
    ):
        future_year = date.today().year + 1
        with pytest.raises(InvalidLastYear):
            available_years.return_range_years(2020, future_year)

    def test_return_range_years_with_last_year_before_initial_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidLastYear):
            available_years.return_range_years(2020, 2019)

    def test_return_range_years_with_non_integer_initial_year_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidFirstYear):
            available_years.return_range_years('2020', 2021)

    def test_return_range_years_with_float_initial_year_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidFirstYear):
            available_years.return_range_years(2020.5, 2021)

    def test_return_range_years_with_non_integer_last_year_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidLastYear):
            available_years.return_range_years(2020, '2021')

    def test_return_range_years_with_float_last_year_raises_error(
        self, available_years
    ):
        with pytest.raises(InvalidLastYear):
            available_years.return_range_years(2020, 2021.5)

    def test_return_range_years_with_none_values_uses_defaults(
        self, available_years
    ):
        years_range = available_years.return_range_years(None, None)

        assert years_range.start == 2010
        assert years_range.stop == date.today().year + 1

    def test_return_range_years_with_minimum_year_2010(self, available_years):
        years_range = available_years.return_range_years(2010, 2015)

        assert 2010 in list(years_range)

    def test_return_range_years_with_current_year(self, available_years):
        current_year = date.today().year
        years_range = available_years.return_range_years(2020, current_year)

        assert current_year in list(years_range)

    def test_return_range_years_respects_mocked_current_year(
        self, available_years, monkeypatch
    ):
        fake_date = Mock()
        fake_date.today.return_value = date(2023, 7, 1)
        monkeypatch.setattr(core, 'date', fake_date)

        assert available_years.get_current_year() == 2023
        years_range = available_years.return_range_years()
        assert list(years_range)[-1] == 2023

    def test_return_range_years_with_year_2002_raises_invalid_first_year(
        self, available_years
    ):
        with pytest.raises(InvalidFirstYear) as exc_info:
            available_years.return_range_years(2002, 2020)

        assert '2003' in str(exc_info.value)

    def test_return_range_years_with_reversed_years_raises_invalid_last_year(
        self, available_years
    ):
        with pytest.raises(InvalidLastYear) as exc_info:
            available_years.return_range_years(2022, 2020)

        assert str(exc_info.value)

    def test_return_range_years_consecutive_years(self, available_years):
        years_range = available_years.return_range_years(2020, 2021)
        years_list = list(years_range)

        assert years_list == [2020, 2021]

    def test_return_range_years_large_range(self, available_years):
        years_range = available_years.return_range_years(2010, 2024)
        years_list = list(years_range)

        assert len(years_list) == 15
        assert years_list[0] == 2010
        assert years_list[-1] == 2024

    def test_return_range_years_iterable(self, available_years):
        years_range = available_years.return_range_years(2020, 2023)

        count = 0
        for year in years_range:
            assert isinstance(year, int)
            count += 1

        assert count == 4

    def test_return_range_years_can_be_converted_to_list(
        self, available_years
    ):
        years_range = available_years.return_range_years(2020, 2022)
        years_list = list(years_range)

        assert isinstance(years_list, list)
        assert all(isinstance(year, int) for year in years_list)

    def test_return_range_years_with_boundary_year_2010(self, available_years):
        years_range = available_years.return_range_years(2010, 2011)

        assert 2010 in list(years_range)

    def test_return_range_years_error_messages_contain_year_info(
        self, available_years
    ):
        with pytest.raises(InvalidFirstYear) as exc_info:
            available_years.return_range_years(2000, 2020)

        error_message = str(exc_info.value)
        assert '2010' in error_message or 'first year' in error_message.lower()

    def test_invalid_first_year_with_boolean(self, available_years):
        with pytest.raises(InvalidFirstYear):
            available_years.return_range_years(True, 2020)

    def test_invalid_last_year_with_list(self, available_years):
        with pytest.raises(InvalidLastYear):
            available_years.return_range_years(2020, [2021])

    def test_return_range_years_minimum_boundary(self, available_years):
        years_range = available_years.return_range_years(2010, 2010)
        assert list(years_range) == [2010]

    def test_return_range_years_maximum_boundary(self, available_years):
        current_year = date.today().year
        years_range = available_years.return_range_years(
            current_year, current_year
        )
        assert list(years_range) == [current_year]

    def test_constants_relationship(self, available_years):
        assert (
            available_years.get_minimal_general_year()
            < available_years.get_minimal_itr_year()
        )
        assert (
            available_years.get_minimal_itr_year()
            < available_years.get_minimal_cgvn_vlmo_year()
        )
        assert (
            available_years.get_minimal_cgvn_vlmo_year()
            <= available_years.get_current_year()
        )
