"""Execute the bilingual incremental examples with controlled downloads."""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from typing import Any

import pytest

import globaldatafinance
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)

pytestmark = pytest.mark.integration


@pytest.fixture(params=['cvm-docs.md', 'cvm-docs.en.md'])
def incremental_example(tmp_path: Path, request: Any) -> Path:
    """Materialize the documented Python block with a caller-owned path."""
    repository = Path(__file__).resolve().parents[3]
    page = repository / 'docs' / 'user-guide' / request.param
    blocks = re.findall(
        r'```python\n(.*?)\n```', page.read_text(encoding='utf-8'), re.DOTALL
    )
    code = next(block for block in blocks if 'checkpoint =' in block)
    script = tmp_path / 'incremental.py'
    script.write_text(
        code.replace('Path("/data/cvm")', f'Path({str(tmp_path / "data")!r})'),
        encoding='utf-8',
    )
    return script


@pytest.fixture
def incremental_client(
    monkeypatch: pytest.MonkeyPatch,
) -> FundamentalStocksDataCVM:
    """Keep real facade orchestration while fixing the example's year range."""
    client = FundamentalStocksDataCVM()
    years = client.get_available_years()._replace(current_year=2024)
    monkeypatch.setattr(client, 'get_available_years', lambda: years)
    monkeypatch.setattr(
        globaldatafinance, 'FundamentalStocksDataCVM', lambda: client
    )
    return client


@pytest.fixture
def controlled_downloads(
    incremental_client: FundamentalStocksDataCVM,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[int], set[int]]:
    """Replace the transport boundary with success or one-shot failure."""
    requested: list[int] = []
    failures: set[int] = set()

    def download(tasks, *, automatic_extractor):
        assert automatic_extractor is True
        result = DownloadResultCVM()
        for _, doc, year, _ in tasks:
            requested.append(int(year))
            identifier = f'{doc}_{year}'
            if int(year) in failures:
                failures.remove(int(year))
                result.add_error_downloads(
                    identifier, 'Controlled network failure'
                )
            else:
                result.add_success_downloads(identifier)
        return result

    monkeypatch.setattr(
        incremental_client.download_adapter, 'download_docs', download
    )
    return requested, failures


def test_incremental_example_retries_failed_year_despite_its_empty_directory(
    tmp_path: Path,
    incremental_example: Path,
    controlled_downloads: tuple[list[int], set[int]],
) -> None:
    """Only successful results survive restart as completed identifiers."""
    destination = tmp_path / 'data'
    destination.mkdir()
    checkpoint = destination / 'completed-downloads.json'
    checkpoint.write_text(
        json.dumps(['DFP_2020', 'DFP_2022', 'DFP_2023']), encoding='utf-8'
    )
    requested, failures = controlled_downloads
    failures.add(2021)
    runpy.run_path(str(incremental_example))

    assert requested == [2021, 2024]
    assert list((destination / 'DFP' / '2021').iterdir()) == []
    assert 'DFP_2021' not in json.loads(checkpoint.read_text(encoding='utf-8'))

    runpy.run_path(str(incremental_example))

    assert requested == [2021, 2024, 2021, 2024]
    assert json.loads(checkpoint.read_text(encoding='utf-8')) == [
        f'DFP_{year}' for year in range(2020, 2025)
    ]
    assert not checkpoint.with_suffix('.tmp').exists()


def test_incremental_example_respects_sparse_gaps_and_refreshes_current_year(
    tmp_path: Path,
    incremental_example: Path,
    controlled_downloads: tuple[list[int], set[int]],
) -> None:
    """A completed intervening year is skipped and refresh is explicit."""
    destination = tmp_path / 'data'
    destination.mkdir()
    checkpoint = destination / 'completed-downloads.json'
    checkpoint.write_text(
        json.dumps(['DFP_2020', 'DFP_2022', 'DFP_2024']), encoding='utf-8'
    )
    requested, _ = controlled_downloads

    runpy.run_path(str(incremental_example))

    assert requested == [2021, 2023, 2024]
    assert json.loads(checkpoint.read_text(encoding='utf-8')) == [
        f'DFP_{year}' for year in range(2020, 2025)
    ]
