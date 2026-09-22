"""Public B3 writer compatibility tests using Arrow runtime facilities."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    session as b3_session,
)
from globaldatafinance.macro_exceptions import ParquetWriteError
from globaldatafinance.macro_infra.temporary_files import (
    reserve_temporary_path,
)

pytestmark = pytest.mark.integration


def _record(ticker: str) -> dict[str, object]:
    """Build one B3 record accepted by the stable public writer."""
    decimal = Decimal('123.45')
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


@pytest.mark.asyncio
async def test_overwrite_writes_canonical_arrow_schema(tmp_path: Path) -> None:
    """Overwrite validates Arrow values and publishes only the final file."""
    output = tmp_path / 'quotes.parquet'

    await parquet_writer.ParquetWriterB3().write_to_parquet(
        [_record('PETR4')], output
    )

    parquet = pq.ParquetFile(output)
    assert parquet.schema_arrow == parquet_writer.build_b3_schema()
    assert parquet.read()['ticker'].to_pylist() == ['PETR4']
    assert output.with_suffix('.parquet.tmp').exists() is False


@pytest.mark.asyncio
async def test_append_copies_existing_batches_once_then_appends(
    tmp_path: Path,
) -> None:
    """The public append operation replaces a validated temporary artifact."""
    output = tmp_path / 'quotes.parquet'
    writer = parquet_writer.ParquetWriterB3()
    await writer.write_to_parquet([_record('PETR4')], output)

    await writer.write_to_parquet([_record('VALE3')], output, mode='append')

    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


@pytest.mark.asyncio
async def test_append_rejects_an_existing_noncanonical_schema(
    tmp_path: Path,
) -> None:
    """Append cannot silently cast an unrelated Parquet contract."""
    output = tmp_path / 'quotes.parquet'
    pq.write_table(pa.table({'wrong': [1]}), output)

    with pytest.raises(ParquetWriteError, match='schema is incompatible'):
        await parquet_writer.ParquetWriterB3().write_to_parquet(
            [_record('PETR4')], output, mode='append'
        )

    assert pq.ParquetFile(output).schema_arrow.names == ['wrong']


def test_public_writer_allocates_distinct_same_directory_temporary_paths(
    tmp_path: Path,
) -> None:
    """Concurrent public writes cannot share a temporary artifact name."""
    output = tmp_path / 'quotes.parquet'

    first = reserve_temporary_path(output, suffix='.parquet.tmp')
    second = reserve_temporary_path(output, suffix='.parquet.tmp')
    try:
        assert first != second
        assert first.parent == second.parent == tmp_path
        assert first.name.endswith('.parquet.tmp')
        assert second.name.endswith('.parquet.tmp')
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_public_writer_preserves_a_large_caller_list_in_bounded_slices(
    tmp_path: Path,
) -> None:
    """The compatibility writer preserves its list with bounded slices."""
    record_count = b3_session.RECORD_BATCH_LIMIT + 1
    records = [_record(f'GD{index:010d}') for index in range(record_count)]
    output = tmp_path / 'quotes.parquet'

    await parquet_writer.ParquetWriterB3().write_to_parquet(records, output)

    table = pq.read_table(output, columns=['ticker'])
    assert len(records) == record_count
    assert records[0]['ticker'] == 'GD0000000000'
    assert records[-1]['ticker'] == f'GD{record_count - 1:010d}'
    assert table['ticker'].to_pylist() == [
        f'GD{index:010d}' for index in range(record_count)
    ]
