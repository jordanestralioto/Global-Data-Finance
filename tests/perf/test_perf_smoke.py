"""Opt-in performance smoke checks for local CVM URLs and B3 parsing.

These kernels exercise pure computation without source downloads or I/O.

Save a baseline::

    uv run --locked --no-sync pytest tests/perf -m perf --benchmark-save=v1

Compare with the baseline::

    uv run --locked --no-sync pytest tests/perf -m perf --benchmark-compare=v1
"""

from __future__ import annotations

from typing import Any

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import CotahistParserB3
from globaldatafinance.brazil.cvm.fundamental_stocks_data.client import (
    generate_urls,
)
from tests.support.builders import build_cotahist_record

pytestmark = [pytest.mark.perf, pytest.mark.slow]


def test_benchmark_cvm_url_generation(benchmark) -> None:
    """Benchmark generating CVM download URLs for a 3-year DFP range.

    Pure-compute path: hits `DictZipsToDownloadCVM` value object logic
    without touching the network.
    """

    def _run() -> int:
        dict_zips, _ = generate_urls(
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2022,
        )
        return sum(len(urls) for urls in dict_zips.values())

    total_urls = benchmark(_run)
    assert total_urls > 0


def test_benchmark_b3_cotahist_parse_line(benchmark) -> None:
    """Benchmark parsing a single COTAHIST line through the full pipeline.

    Pure-compute path: exercises slicing, decimal parsing and date parsing.
    """
    parser = CotahistParserB3()
    line = build_cotahist_record(year=2024, ticker='PETR4', market='010')
    target_codes = {'010', '020'}

    def _run() -> dict[str, Any] | None:
        return parser.parse_line(line, target_codes)

    parsed = benchmark(_run)
    assert parsed is not None
    assert parsed['ticker'] == 'PETR4'
