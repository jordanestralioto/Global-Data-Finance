"""Unit tests for deterministic caller-owned COTAHIST year selection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from tests.brazil.b3_data.historical_quotes import conftest as fixture_module
from tests.brazil.b3_data.historical_quotes.integration import (
    test_real_cotahist as real_cotahist_module,
)

pytestmark = pytest.mark.unit


def test_missing_dataset_skip_message_has_a_self_contained_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recovery hint names both required local COTAHIST variables."""
    monkeypatch.delenv('COTAHIST_PATH', raising=False)

    with pytest.raises(
        pytest.skip.Exception, match='COTAHIST_PATH is not set'
    ) as error:
        fixture_module._configured_dataset_path()

    assert (
        'COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2023 '
        'uv run --locked --no-sync pytest -m "real_data and not slow"'
    ) in str(error.value)


def test_selects_the_only_available_year_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A one-year caller dataset remains ergonomic without an env override."""
    monkeypatch.delenv('COTAHIST_TEST_YEAR', raising=False)

    selected_year = fixture_module._selected_year({2000: [Path('2000.zip')]})

    assert selected_year == 2000


def test_selects_the_explicit_year_from_a_multi_year_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit year is propagated rather than selecting the newest file."""
    monkeypatch.setenv('COTAHIST_TEST_YEAR', '2000')

    selected_year = fixture_module._selected_year(
        {2000: [Path('2000.zip')], 2024: [Path('2024.zip')]}
    )

    assert selected_year == 2000


def test_rejects_ambiguous_catalog_without_an_explicit_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple local years require a deliberate caller selection."""
    monkeypatch.delenv('COTAHIST_TEST_YEAR', raising=False)

    with pytest.raises(pytest.fail.Exception, match='multiple years'):
        fixture_module._selected_year(
            {2000: [Path('2000.zip')], 2024: [Path('2024.zip')]}
        )


def test_collect_quote_sample_accepts_fewer_than_the_upper_bound(
    tmp_path: Path,
) -> None:
    """A small valid input remains useful for bounded parity coverage."""
    input_file = tmp_path / 'COTAHIST_A2024.ZIP'
    with zipfile.ZipFile(input_file, 'w') as archive:
        archive.writestr(
            'COTAHIST_A2024.TXT', '99ignored\n01first\n01second\n'
        )

    sampled = real_cotahist_module._collect_quote_sample(input_file)

    assert sampled == ['01first', '01second']


def test_collect_quote_sample_rejects_input_without_type_01_records(
    tmp_path: Path,
) -> None:
    """An empty parity sample fails instead of silently passing."""

    input_file = tmp_path / 'COTAHIST_A2024.ZIP'
    with zipfile.ZipFile(input_file, 'w') as archive:
        archive.writestr('COTAHIST_A2024.TXT', '99header\n')

    with pytest.raises(ExtractionError, match='no type-01 quote data record'):
        real_cotahist_module._collect_quote_sample(input_file)
