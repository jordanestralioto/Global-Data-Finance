"""Ordered, non-destructive merge tests for B3 transaction artifacts."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
    parquet_writer,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.integration


def _record(ticker: str) -> dict[str, object]:
    """Build a complete typed record accepted by the canonical B3 schema."""
    decimal = Decimal('1.23')
    return {
        'data_pregao': date(2024, 1, 2),
        'codigo_bdi': '02',
        'ticker': ticker,
        'tipo_mercado': '010',
        'nome_resumido': ticker,
        'especificacao_papel': 'ON',
        'preco_abertura': decimal,
        'preco_maximo': decimal,
        'preco_minimo': decimal,
        'preco_medio': decimal,
        'preco_fechamento': decimal,
        'melhor_oferta_compra': decimal,
        'melhor_oferta_venda': decimal,
        'numero_negocios': 1,
        'quantidade_total': 2,
        'volume_total': decimal,
        'data_vencimento': None,
        'fator_cotacao': 1,
        'codigo_isin': 'BRTESTE00001',
        'numero_distribuicao': 1,
    }


def _write(path: Path, ticker: str) -> None:
    """Create one source temporary artifact through its persistent session."""
    session = parquet_writer.B3ParquetWriterSession().open(
        path, parquet_writer.build_b3_schema()
    )
    records = [_record(ticker)]
    session.write_records(records)
    session.close()


def test_merge_preserves_source_order_and_temporary_inputs(
    tmp_path: Path,
) -> None:
    """A merge copies batches in caller order and cleans up only at commit."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    output = tmp_path / 'merged.parquet'
    _write(first, 'PETR4')
    _write(second, 'VALE3')

    rows = extraction_service.merge_temp_files_streaming(
        [first, second], output, parquet_writer.build_b3_schema()
    )

    assert rows == 2
    assert first.exists() and second.exists()
    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


def test_merge_writes_a_valid_empty_schema_when_no_source_has_matches(
    tmp_path: Path,
) -> None:
    """An all-filtered request still produces a valid empty B3 Parquet."""
    output = tmp_path / 'empty.parquet'
    schema = parquet_writer.build_b3_schema()

    rows = extraction_service.merge_temp_files_streaming([], output, schema)

    parquet = pq.ParquetFile(output)
    assert rows == parquet.metadata.num_rows == 0
    assert parquet.schema_arrow == schema


def test_merge_rejects_schema_mismatch_without_deleting_source_artifacts(
    tmp_path: Path,
) -> None:
    """Invalid temporary schema cannot be promoted or destroy diagnostics."""
    invalid = tmp_path / 'invalid.parquet'
    pq.write_table(pa.table({'wrong': [1]}), invalid)
    output = tmp_path / 'merged.parquet'

    with pytest.raises(ExtractionError, match='schema is incompatible'):
        extraction_service.merge_temp_files_streaming(
            [invalid], output, parquet_writer.build_b3_schema()
        )

    assert invalid.exists()
    assert output.exists() is False


def test_merge_rejects_a_temporary_row_count_mismatch(
    tmp_path: Path,
) -> None:
    """A valid schema is insufficient when source row metrics disagree."""
    source = tmp_path / 'source.parquet'
    output = tmp_path / 'merged.parquet'
    _write(source, 'PETR4')

    with pytest.raises(ExtractionError, match='row count is incompatible'):
        extraction_service.merge_temp_files_streaming(
            [source],
            output,
            parquet_writer.build_b3_schema(),
            expected_rows=[2],
        )

    assert source.exists()
    assert output.exists() is False
