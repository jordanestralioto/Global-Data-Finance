"""Source-local parser state tests used by B3 workers."""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
)
from tests.support.builders import build_cotahist_record

pytestmark = pytest.mark.unit


def test_parser_metrics_are_isolated_between_worker_instances() -> None:
    """Parallel sources cannot share mutable classification counters."""
    selected = CotahistParserB3()
    filtered = CotahistParserB3()

    assert selected.parse_line(build_cotahist_record(), {'010'}) is not None
    assert (
        filtered.parse_line(build_cotahist_record(market='070'), {'010'})
        is None
    )

    assert selected.metrics.parsed_records == 1
    assert selected.metrics.filtered_records == 0
    assert filtered.metrics.parsed_records == 0
    assert filtered.metrics.filtered_records == 1
