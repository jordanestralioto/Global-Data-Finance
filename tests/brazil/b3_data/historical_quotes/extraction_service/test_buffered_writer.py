"""Regression tests for bounded source output ownership."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)

pytestmark = pytest.mark.integration


def test_session_clears_a_large_input_list_as_it_converts_batches(
    tmp_path: Path,
) -> None:
    """The writer clears caller dictionaries after a flush."""
    record = {
        'data_pregao': date(2024, 1, 2),
        'codigo_bdi': '02',
        'ticker': 'PETR4',
        'tipo_mercado': '010',
        'nome_resumido': 'PETROBRAS',
        'especificacao_papel': 'ON',
        'preco_abertura': Decimal('1.00'),
        'preco_maximo': Decimal('1.00'),
        'preco_minimo': Decimal('1.00'),
        'preco_medio': Decimal('1.00'),
        'preco_fechamento': Decimal('1.00'),
        'melhor_oferta_compra': Decimal('1.00'),
        'melhor_oferta_venda': Decimal('1.00'),
        'numero_negocios': 1,
        'quantidade_total': 1,
        'volume_total': Decimal('1.00'),
        'data_vencimento': None,
        'fator_cotacao': 1,
        'codigo_isin': 'BRPETRACNPR6',
        'numero_distribuicao': 1,
    }
    records = [record.copy() for _ in range(3)]
    session = parquet_writer.B3ParquetWriterSession(row_group_limit=2).open(
        tmp_path / 'quotes.parquet', parquet_writer.build_b3_schema()
    )

    session.write_records(records)
    session.close()

    assert records == []
    assert session.rows_written == 3
