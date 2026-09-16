"""Persistent Arrow session regressions for B3 row groups."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.integration


def _record(index: int) -> dict[str, object]:
    """Build one canonical B3 data row."""
    decimal = Decimal(f'{index}.01')
    return {
        'data_pregao': date(2024, 1, 2),
        'codigo_bdi': '02',
        'ticker': f'T{index:05d}',
        'tipo_mercado': '010',
        'nome_resumido': 'TEST',
        'especificacao_papel': 'ON',
        'preco_abertura': decimal,
        'preco_maximo': decimal,
        'preco_minimo': decimal,
        'preco_medio': decimal,
        'preco_fechamento': decimal,
        'melhor_oferta_compra': decimal,
        'melhor_oferta_venda': decimal,
        'numero_negocios': index,
        'quantidade_total': index,
        'volume_total': decimal,
        'data_vencimento': None,
        'fator_cotacao': 1,
        'codigo_isin': 'BRTESTE00001',
        'numero_distribuicao': 1,
    }


def test_session_flushes_bounded_row_groups_and_clears_python_records(
    tmp_path: Path,
) -> None:
    """No reopen/append cycle is needed to write multiple groups."""
    output = tmp_path / 'quotes.parquet'
    session = parquet_writer.B3ParquetWriterSession(row_group_limit=2).open(
        output, parquet_writer.build_b3_schema()
    )
    records = [_record(1), _record(2), _record(3)]

    session.write_records(records)
    session.close()

    metadata = pq.ParquetFile(output).metadata
    assert records == []
    assert session.rows_written == metadata.num_rows == 3
    assert [metadata.row_group(index).num_rows for index in range(2)] == [2, 1]


def test_session_lifecycle_rejects_reopen_and_keeps_new_close_nonterminal(
    tmp_path: Path,
) -> None:
    """NEW can recover from its required-open error, CLOSED cannot reopen."""
    session = parquet_writer.B3ParquetWriterSession()

    with pytest.raises(RuntimeError, match='has not been opened'):
        session.close()
    assert session.state == 'NEW'

    session.open(tmp_path / 'quotes.parquet', parquet_writer.build_b3_schema())
    session.close()

    assert session.state == 'CLOSED'
    session.close()
    with pytest.raises(RuntimeError, match='only be opened from NEW'):
        session.open(
            tmp_path / 'other.parquet', parquet_writer.build_b3_schema()
        )


def test_failed_open_clears_partial_state_and_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A constructor failure leaves no half-open session state behind."""

    class _FailingParquet:
        def ParquetWriter(self, *_args: object, **_kwargs: object) -> object:
            raise OSError('writer construction failed')

    monkeypatch.setattr(
        parquet_writer.session,
        '_get_arrow',
        lambda: (pa, object(), _FailingParquet()),
    )
    session = parquet_writer.B3ParquetWriterSession()
    schema = parquet_writer.build_b3_schema()

    with pytest.raises(OSError, match='writer construction failed'):
        session.open(tmp_path / 'failed.parquet', schema)

    assert session.state == 'NEW'
    assert session.path is None
    assert session.schema is None
    assert session._writer is None
    assert not (tmp_path / 'failed.parquet').exists()

    monkeypatch.undo()
    session.open(tmp_path / 'retry.parquet', schema).close()
    assert session.state == 'CLOSED'


def test_failed_close_is_terminal_and_clears_pending_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation errors close the resource and forbid a second open."""
    session = parquet_writer.B3ParquetWriterSession().open(
        tmp_path / 'quotes.parquet', parquet_writer.build_b3_schema()
    )
    session.write_records([_record(1)])

    def fail_validation() -> None:
        raise ExtractionError('B3 Parquet', 'injected validation failure')

    monkeypatch.setattr(session, 'validate', fail_validation)
    with pytest.raises(ExtractionError, match='injected validation failure'):
        session.close()

    assert session.state == 'CLOSED'
    assert session._writer is None
    assert session._pending_batches == []
    with pytest.raises(RuntimeError, match='only be opened from NEW'):
        session.open(
            tmp_path / 'other.parquet', parquet_writer.build_b3_schema()
        )


def test_session_rejects_batches_with_a_different_schema(
    tmp_path: Path,
) -> None:
    """A source schema mismatch stops the merge before publication."""
    session = parquet_writer.B3ParquetWriterSession().open(
        tmp_path / 'quotes.parquet', parquet_writer.build_b3_schema()
    )
    invalid = pa.record_batch({'wrong': [1]})

    with pytest.raises(ExtractionError, match='schema is incompatible'):
        session.write_batches([invalid])

    session.close()


def test_session_preserves_empty_optional_strings_as_empty_strings(
    tmp_path: Path,
) -> None:
    """Empty B3 text fields are distinct from absent nullable values."""
    output = tmp_path / 'quotes.parquet'
    record = _record(1)
    record.update(
        {
            'codigo_bdi': '',
            'nome_resumido': '',
            'especificacao_papel': '',
            'codigo_isin': '',
        }
    )
    session = parquet_writer.B3ParquetWriterSession().open(
        output, parquet_writer.build_b3_schema()
    )

    session.write_records([record])
    session.close()

    row = pq.read_table(output).to_pylist()[0]
    assert row['codigo_bdi'] == ''
    assert row['nome_resumido'] == ''
    assert row['especificacao_papel'] == ''
    assert row['codigo_isin'] == ''
    assert row['data_vencimento'] is None


def test_public_record_and_canonical_row_reject_reserved_null_sentinel(
    tmp_path: Path,
) -> None:
    """The private null marker cannot be smuggled in as real B3 data."""
    reserved = '__GLOBALDATAFINANCE_NULL__'
    schema = parquet_writer.build_b3_schema()

    record_output = tmp_path / 'record.parquet'
    record_session = parquet_writer.B3ParquetWriterSession().open(
        record_output, schema
    )
    record = _record(1)
    record['ticker'] = reserved
    with pytest.raises(ExtractionError, match='column='):
        record_session.write_records([record])
    record_session.close()

    row_output = tmp_path / 'row.parquet'
    row_session = parquet_writer.B3ParquetWriterSession().open(
        row_output, schema
    )
    row = [''] * len(schema.names)
    row[schema.get_field_index('ticker')] = reserved
    with pytest.raises(ExtractionError, match='row=1; column='):
        row_session.write_csv_rows([tuple(row)])
    row_session.close()
