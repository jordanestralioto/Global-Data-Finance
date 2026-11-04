"""Observe converted Arrow values before any buffering or persistence."""

from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    parquet_writer,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    session as writer_session,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _rows():
    parser = CotahistParserB3()
    rows = []
    for ticker in ('PETR4', 'VALE3', 'PETR4'):
        row = parser.parse_line_to_csv_row(
            build_cotahist_record(ticker=ticker), {'010'}
        )
        assert row is not None
        rows.append(row)
    return rows


def test_batch_observer_runs_once_before_buffering_and_flushing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each converted batch is observed before its row group can be written."""
    monkeypatch.setattr(writer_session, 'RECORD_BATCH_LIMIT', 2)
    output = tmp_path / 'observed.parquet'
    session = parquet_writer.B3ParquetWriterSession(row_group_limit=1).open(
        output, parquet_writer.build_b3_schema()
    )
    observations = []

    def observe(batch):
        observations.append(
            (batch.num_rows, session.rows_written, session._pending_rows)
        )

    rows = _rows()
    session.write_csv_rows(rows, batch_observer=observe)
    session.close()
    assert rows == []
    assert observations == [(2, 0, 0), (1, 2, 0)]
    assert pq.read_table(output)['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
        'PETR4',
    ]


def test_observer_failure_clears_input_before_propagating(
    tmp_path: Path,
) -> None:
    """A failed observer preserves its diagnostic and releases Python rows."""
    session = parquet_writer.B3ParquetWriterSession().open(
        tmp_path / 'failed.parquet', parquet_writer.build_b3_schema()
    )
    rows = _rows()

    def fail(_batch):
        raise RuntimeError('injected observer failure')

    try:
        with pytest.raises(RuntimeError, match='injected observer failure'):
            session.write_csv_rows(rows, batch_observer=fail)
        assert rows == []
        assert session._pending_rows == 0
    finally:
        session.close()


def test_converted_value_mutation_cannot_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker digest covers Arrow values independently of parser output."""
    write_cotahist_txt(tmp_path, year=2024, records=[build_cotahist_record()])
    original = writer_session.B3ParquetWriterSession._csv_rows_to_batches

    def alter(rows, schema, **kwargs):
        batches = original(rows, schema, **kwargs)
        index = schema.get_field_index('ticker')
        return [
            batch.set_column(
                index,
                schema.field(index),
                pa.array(
                    ['CHANGED'] * batch.num_rows, type=schema.field(index).type
                ),
            )
            for batch in batches
        ]

    monkeypatch.setattr(
        writer_session.B3ParquetWriterSession,
        '_csv_rows_to_batches',
        staticmethod(alter),
    )
    result = HistoricalQuotesB3().extract(
        str(tmp_path), initial_year=2024, last_year=2024, verbose=False
    )
    assert result['success'] is False
    assert any(
        'selected-row digest changed' in error
        for error in result['errors'].values()
    )
    assert result['output_file'] == ''
    assert not list(tmp_path.glob('*.parquet'))
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.parametrize('row_delta', [-1, 1])
def test_converted_row_count_mismatch_is_rejected_before_provenance(
    monkeypatch: pytest.MonkeyPatch, row_delta: int
) -> None:
    """Conversion cannot attach original bytes to a different set of rows."""
    read_csv = pacsv.read_csv

    def change_count(*args, **kwargs):
        table = read_csv(*args, **kwargs)
        if row_delta < 0:
            return table.slice(1)
        return pa.concat_tables([table, table.slice(0, 1)])

    monkeypatch.setattr(pacsv, 'read_csv', change_count)
    with pytest.raises(
        ExtractionError,
        match=f'row count.*expected=3; observed={3 + row_delta}',
    ):
        writer_session.B3ParquetWriterSession._csv_rows_to_batches(
            _rows(), parquet_writer.build_b3_schema()
        )
