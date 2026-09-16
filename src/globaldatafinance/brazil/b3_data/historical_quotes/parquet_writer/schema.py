"""Lazy construction of the canonical B3 Arrow schema."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyarrow import Schema

B3_STRING_COLUMNS = (
    'codigo_bdi',
    'ticker',
    'tipo_mercado',
    'nome_resumido',
    'especificacao_papel',
    'codigo_isin',
)
B3_DECIMAL_COLUMNS = (
    'preco_abertura',
    'preco_maximo',
    'preco_minimo',
    'preco_medio',
    'preco_fechamento',
    'melhor_oferta_compra',
    'melhor_oferta_venda',
    'volume_total',
)
B3_INT_COLUMNS = (
    'numero_negocios',
    'quantidade_total',
    'fator_cotacao',
    'numero_distribuicao',
)
B3_DATE_COLUMNS = ('data_pregao', 'data_vencimento')
B3_COLUMNS = (
    'data_pregao',
    'codigo_bdi',
    'ticker',
    'tipo_mercado',
    'nome_resumido',
    'especificacao_papel',
    'preco_abertura',
    'preco_maximo',
    'preco_minimo',
    'preco_medio',
    'preco_fechamento',
    'melhor_oferta_compra',
    'melhor_oferta_venda',
    'numero_negocios',
    'quantidade_total',
    'volume_total',
    'data_vencimento',
    'fator_cotacao',
    'codigo_isin',
    'numero_distribuicao',
)


def build_b3_schema() -> Schema:
    """Build the logical B3 schema only when a writer starts work."""
    import pyarrow as pa

    decimal = pa.decimal128(38, 2)
    column_types = {
        **{name: pa.date32() for name in B3_DATE_COLUMNS},
        **{name: pa.large_string() for name in B3_STRING_COLUMNS},
        **dict.fromkeys(B3_DECIMAL_COLUMNS, decimal),
        **{name: pa.int64() for name in B3_INT_COLUMNS},
    }
    return pa.schema(
        [pa.field(name, column_types[name]) for name in B3_COLUMNS]
    )


def schema_fingerprint(schema: Schema) -> str:
    """Return a stable logical-schema fingerprint for transaction manifests."""
    return hashlib.sha256(schema.to_string().encode('utf-8')).hexdigest()
