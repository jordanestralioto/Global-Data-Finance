"""Regression tests for bounded source output ownership."""

from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from tests.support.builders import build_b3_typed_record

pytestmark = pytest.mark.integration


def test_session_clears_a_large_input_list_as_it_converts_batches(
    tmp_path: Path,
) -> None:
    """The writer clears caller dictionaries after a flush."""
    record = build_b3_typed_record()
    records = [record.copy() for _ in range(3)]
    session = parquet_writer.B3ParquetWriterSession(row_group_limit=2).open(
        tmp_path / 'quotes.parquet', parquet_writer.build_b3_schema()
    )

    session.write_records(records)
    session.close()

    assert records == []
    assert session.rows_written == 3
