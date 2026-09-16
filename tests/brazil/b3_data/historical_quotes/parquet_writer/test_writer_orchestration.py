"""Public writer error and empty-output orchestration tests."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_writer_publishes_an_empty_canonical_b3_output(
    tmp_path: Path,
) -> None:
    """An all-filtered extraction has an empty Parquet contract."""
    output = tmp_path / 'empty.parquet'

    await parquet_writer.ParquetWriterB3().write_to_parquet([], output)

    parquet = pq.ParquetFile(output)
    assert parquet.metadata.num_rows == 0
    assert parquet.schema_arrow == parquet_writer.build_b3_schema()


@pytest.mark.asyncio
async def test_writer_rejects_an_unknown_write_mode(tmp_path: Path) -> None:
    """The stable public method has only overwrite and append semantics."""
    with pytest.raises(ValueError, match='Unsupported Parquet write mode'):
        await parquet_writer.ParquetWriterB3().write_to_parquet(
            [], tmp_path / 'quotes.parquet', mode='merge'
        )
