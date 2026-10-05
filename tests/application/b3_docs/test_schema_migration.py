"""Regeneration keeps legacy output available for consumer rollback."""

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from scripts.cotahist_oracle import reconcile_sources
from scripts.cotahist_oracle.row_decoder import decode_quote
from scripts.cotahist_oracle.schema import independent_schema
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.integration


def test_regeneration_preserves_legacy_file_and_verified_values(
    tmp_path: Path,
) -> None:
    """A separate v2 output adds missing rows without modifying v1 bytes."""
    sources = tmp_path / 'sources'
    sources.mkdir()
    quote = build_cotahist_record(year=2024, ticker='PETR4')
    source = write_cotahist_zip(
        sources,
        year=2024,
        records=[quote, build_cotahist_record(year=2024, market='021')],
    )
    legacy_schema = pa.schema(list(independent_schema())[:20])
    row = decode_quote(
        quote.encode('latin-1'),
        source_name=source.name,
        member='COTAHIST_A2024.TXT',
        year=2024,
        line_number=2,
        content_sha256='',
    )
    legacy_table = pa.Table.from_pylist([row], schema=legacy_schema)
    previous_output = tmp_path / 'v1.parquet'
    pq.write_table(legacy_table, previous_output)
    previous_sha256 = hashlib.sha256(previous_output.read_bytes()).hexdigest()

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(sources),
        initial_year=2024,
        last_year=2024,
        destination_path=str(tmp_path / 'v2'),
        verbose=False,
    )

    assert result['success'] is True
    assert result['schema_version'] == 2
    assert result['total_records'] == 2
    new_output = Path(result['output_file'])
    assert new_output != previous_output
    v2 = pq.read_table(new_output)
    assert v2.num_columns == 32
    assert (
        v2.select(legacy_schema.names)
        .slice(0, 1)
        .equals(legacy_table, check_metadata=False)
    )
    reconciliation = reconcile_sources(
        [source], new_output, public_result=dict(result)
    )
    assert reconciliation['previousTwentyFieldsEqual'] is True
    assert reconciliation['blockLotRowsByYear'] == {2024: 1}
    assert hashlib.sha256(previous_output.read_bytes()).hexdigest() == (
        previous_sha256
    )
    assert pq.read_table(previous_output).equals(
        legacy_table, check_metadata=True
    )
