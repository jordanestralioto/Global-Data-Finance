from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.years import (
    YearRangeB3,
)

pytestmark = pytest.mark.unit


class TestYearRangeB3Creation:
    def test_creates_valid_year_range(self):
        initial_year = 2020
        last_year = 2024
        year_range = YearRangeB3(initial_year, last_year)
        assert year_range.initial_year == initial_year
        assert year_range.last_year == last_year

    def test_creates_range_with_same_year(self):
        year = 2020
        year_range = YearRangeB3(year, year)
        assert year_range.initial_year == year
        assert year_range.last_year == year

    def test_creates_range_with_consecutive_years(self):
        initial_year = 2020
        last_year = 2021
        year_range = YearRangeB3(initial_year, last_year)
        assert year_range.initial_year == initial_year
        assert year_range.last_year == last_year

    def test_creates_range_with_large_span(self):
        initial_year = 1986
        last_year = 2024
        year_range = YearRangeB3(initial_year, last_year)
        assert year_range.initial_year == initial_year
        assert year_range.last_year == last_year


class TestYearRangeB3Validation:
    def test_raises_error_for_non_integer_initial_year(self):
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3('2020', 2024)
        assert 'Years must be integers' in str(exc_info.value)

    def test_raises_error_for_non_integer_last_year(self):
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3(2020, '2024')
        assert 'Years must be integers' in str(exc_info.value)

    def test_raises_error_for_float_initial_year(self):
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3(2020.5, 2024)
        assert 'Years must be integers' in str(exc_info.value)

    def test_raises_error_for_float_last_year(self):
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3(2020, 2024.5)
        assert 'Years must be integers' in str(exc_info.value)

    def test_raises_error_for_initial_greater_than_last(self):
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3(2024, 2020)
        assert 'Initial year' in str(exc_info.value)
        assert 'cannot be greater than' in str(exc_info.value)
        assert 'last year' in str(exc_info.value)

    def test_raises_error_for_future_last_year(self):
        future_year = date.today().year + 1
        with pytest.raises(ValueError) as exc_info:
            YearRangeB3(2020, future_year)
        assert 'cannot be in the future' in str(exc_info.value)

    def test_accepts_current_year_as_last_year(self):
        current_year = date.today().year
        year_range = YearRangeB3(2020, current_year)
        assert year_range.last_year == current_year

    def test_raises_error_for_none_initial_year(self):
        with pytest.raises(ValueError):
            YearRangeB3(None, 2024)

    def test_raises_error_for_none_last_year(self):
        with pytest.raises(ValueError):
            YearRangeB3(2020, None)

    def test_raises_error_for_both_none(self):
        with pytest.raises(ValueError):
            YearRangeB3(None, None)

    def test_accepts_old_years(self):
        year_range = YearRangeB3(1986, 2000)
        assert year_range.initial_year == 1986
        assert year_range.last_year == 2000


class TestYearRangeB3Immutability:
    def test_is_frozen_dataclass(self):
        year_range = YearRangeB3(2020, 2024)
        with pytest.raises(FrozenInstanceError):
            year_range.initial_year = 2021

    def test_cannot_modify_last_year(self):
        year_range = YearRangeB3(2020, 2024)
        with pytest.raises(FrozenInstanceError):
            year_range.last_year = 2025

    def test_cannot_add_new_attributes(self):
        year_range = YearRangeB3(2020, 2024)
        with pytest.raises(FrozenInstanceError):
            year_range.new_attribute = 'value'


class TestYearRangeB3ToRange:
    def test_converts_to_python_range(self):
        year_range = YearRangeB3(2020, 2024)
        result = year_range.to_range()
        assert isinstance(result, range)

    def test_range_is_inclusive(self):
        year_range = YearRangeB3(2020, 2024)
        result = list(year_range.to_range())
        assert result == [2020, 2021, 2022, 2023, 2024]

    def test_range_for_single_year(self):
        year_range = YearRangeB3(2020, 2020)
        result = list(year_range.to_range())
        assert result == [2020]

    def test_range_for_consecutive_years(self):
        year_range = YearRangeB3(2020, 2021)
        result = list(year_range.to_range())
        assert result == [2020, 2021]

    def test_range_for_long_span(self):
        year_range = YearRangeB3(1986, 1990)
        result = list(year_range.to_range())
        assert len(result) == 5
        assert result[0] == 1986
        assert result[-1] == 1990

    def test_range_can_be_iterated(self):
        year_range = YearRangeB3(2020, 2022)
        result = year_range.to_range()
        years = []
        for year in result:
            years.append(year)
        assert years == [2020, 2021, 2022]

    def test_range_can_be_used_in_membership_test(self):
        year_range = YearRangeB3(2020, 2024)
        result = year_range.to_range()
        assert 2020 in result
        assert 2022 in result
        assert 2024 in result
        assert 2019 not in result
        assert 2025 not in result


class TestYearRangeB3StringRepresentation:
    def test_str_representation(self):
        year_range = YearRangeB3(2020, 2024)
        result = str(year_range)
        assert result == '2020-2024'

    def test_str_for_single_year(self):
        year_range = YearRangeB3(2020, 2020)
        result = str(year_range)
        assert result == '2020-2020'

    def test_repr_representation(self):
        year_range = YearRangeB3(2020, 2024)
        result = repr(year_range)
        assert 'YearRangeB3' in result
        assert 'initial_year=2020' in result
        assert 'last_year=2024' in result

    def test_repr_is_detailed(self):
        year_range = YearRangeB3(1986, 2024)
        result = repr(year_range)
        assert '1986' in result
        assert '2024' in result


class TestYearRangeB3Equality:
    def test_equal_year_ranges(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2020, 2024)
        assert year_range1 == year_range2

    def test_unequal_year_ranges_different_initial(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2021, 2024)
        assert year_range1 != year_range2

    def test_unequal_year_ranges_different_last(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2020, 2025)
        assert year_range1 != year_range2

    def test_unequal_year_ranges_completely_different(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2015, 2019)
        assert year_range1 != year_range2

    def test_not_equal_to_other_types(self):
        year_range = YearRangeB3(2020, 2024)
        assert year_range != '2020-2024'
        assert year_range != (2020, 2024)
        assert year_range != [2020, 2024]
        assert year_range != range(2020, 2025)


class TestYearRangeB3Hashability:
    def test_is_hashable(self):
        year_range = YearRangeB3(2020, 2024)
        assert hash(year_range) is not None

    def test_can_be_used_in_set(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2015, 2019)
        year_range3 = YearRangeB3(2020, 2024)
        year_set = {year_range1, year_range2, year_range3}
        assert len(year_set) == 2

    def test_can_be_used_as_dict_key(self):
        year_range = YearRangeB3(2020, 2024)
        data = {year_range: 'data for 2020-2024'}
        assert data[year_range] == 'data for 2020-2024'

    def test_equal_ranges_have_same_hash(self):
        year_range1 = YearRangeB3(2020, 2024)
        year_range2 = YearRangeB3(2020, 2024)
        assert hash(year_range1) == hash(year_range2)
