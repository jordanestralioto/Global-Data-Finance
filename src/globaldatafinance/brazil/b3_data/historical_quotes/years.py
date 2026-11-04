"""Year range model and validation for B3 historical quotes."""

from dataclasses import dataclass
from datetime import date

from .errors import InvalidFirstYear, InvalidLastYear


@dataclass(frozen=True)
class YearRangeB3:
    """Immutable value object representing a validated range of years.

    This represents a continuous period of years for which historical
    data should be extracted. Both bounds are inclusive.

    Attributes:
        initial_year: The starting year (inclusive)
        last_year: The ending year (inclusive)

    Examples:
        >>> year_range = YearRangeB3(2020, 2024)
        >>> year_range.initial_year
        2020
        >>> year_range.last_year
        2024
        >>> list(year_range.to_range())
        [2020, 2021, 2022, 2023, 2024]
    """

    initial_year: int
    last_year: int

    def __post_init__(self) -> None:
        """Validate the year range after initialization.

        Raises:
            ValueError: If years are not integers or if the range is invalid
        """
        if not isinstance(self.initial_year, int) or not isinstance(
            self.last_year, int
        ):
            raise ValueError('Years must be integers')

        if self.initial_year > self.last_year:
            raise ValueError(
                f'Initial year ({self.initial_year}) cannot be greater than '
                f'last year ({self.last_year})'
            )

        current_year = date.today().year
        if self.last_year > current_year:
            raise ValueError(
                f'Last year ({self.last_year}) cannot be in the future '
                f'(current year: {current_year})'
            )

    def to_range(self) -> range:
        """Convert the year range to a Python range object.

        Returns:
            range: Python range from initial_year to last_year (inclusive)
        """
        return range(self.initial_year, self.last_year + 1)

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return f'{self.initial_year}-{self.last_year}'

    def __repr__(self) -> str:
        """Return a detailed string representation for debugging."""
        return (
            f'YearRangeB3(initial_year={self.initial_year}, '
            f'last_year={self.last_year})'
        )


class YearValidationServiceB3:
    """Domain service for validating year ranges.

    The B3 COTAHIST files are available starting from 1986.
    """

    __MIN_YEAR = 1986

    @classmethod
    def get_current_year(cls) -> int:
        """Get the current year."""
        return date.today().year

    @classmethod
    def get_min_year(cls) -> int:
        """Get the minimum year for which historical data is available."""
        return cls.__MIN_YEAR

    @classmethod
    def validate_and_create_year_range(
        cls, initial_year: int, last_year: int
    ) -> YearRangeB3:
        """Validate a year range and create a YearRangeB3 value object."""
        current_year = cls.get_current_year()

        if (
            not isinstance(initial_year, int)
            or initial_year < cls.__MIN_YEAR
            or initial_year > current_year
        ):
            raise InvalidFirstYear(cls.__MIN_YEAR, current_year)

        if (
            not isinstance(last_year, int)
            or last_year > current_year
            or initial_year > last_year
        ):
            raise InvalidLastYear(initial_year, current_year)

        return YearRangeB3(initial_year=initial_year, last_year=last_year)
