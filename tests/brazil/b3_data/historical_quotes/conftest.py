from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NoReturn

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    select_cotahist_file,
    validate_cotahist_catalog,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)

_LOCAL_DATA_COMMAND = (
    'COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2023 '
    'uv run --locked --no-sync pytest -m "real_data and not slow"'
)


def _fail(message: str) -> NoReturn:
    pytest.fail(message, pytrace=False)


def configured_dataset_path() -> Path:
    """Return the configured dataset directory or skip the opt-in suite."""
    configured_path = os.environ.get('COTAHIST_PATH')
    if not configured_path:
        pytest.skip(
            'COTAHIST_PATH is not set. Run the opt-in suite with: '
            f'{_LOCAL_DATA_COMMAND}'
        )
    return Path(configured_path).expanduser().resolve()


def selected_year(files_by_year: dict[int, list[Path]]) -> int:
    """Resolve an exact configured year or infer the sole available year."""
    configured_year = os.environ.get('COTAHIST_TEST_YEAR')
    if configured_year is not None:
        if not re.fullmatch(r'\d{4}', configured_year):
            _fail('COTAHIST_TEST_YEAR must be exactly four digits')
        return int(configured_year)
    if len(files_by_year) == 1:
        return next(iter(files_by_year))
    available_years = ', '.join(str(year) for year in sorted(files_by_year))
    _fail(
        'COTAHIST_TEST_YEAR is required when COTAHIST_PATH contains multiple '
        f'years. Available years: {available_years}'
    )


def _select_file(files_by_year: dict[int, list[Path]], year: int) -> Path:
    """Select a deterministic ZIP-first input for the requested year."""
    return select_cotahist_file(files_by_year, year)


@pytest.fixture(scope='session')
def local_cotahist_catalog() -> dict[int, list[Path]]:
    """Index valid caller-owned COTAHIST inputs without processing rows."""
    dataset_path = configured_dataset_path()
    try:
        return validate_cotahist_catalog(dataset_path)
    except CotahistCatalogError as error:
        _fail(str(error))


@pytest.fixture(scope='session')
def local_cotahist(
    local_cotahist_catalog: dict[int, list[Path]],
) -> tuple[Path, int]:
    """Resolve exactly one local year for an opt-in extraction test."""
    files_by_year = local_cotahist_catalog
    year = selected_year(files_by_year)
    if year not in files_by_year:
        available_years = ', '.join(
            str(available_year) for available_year in sorted(files_by_year)
        )
        _fail(
            f'No valid COTAHIST input found for selected year '
            f'{year}. Available years: {available_years}'
        )
    return _select_file(files_by_year, year), year
