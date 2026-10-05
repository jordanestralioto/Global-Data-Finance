"""Define the independent v2 quotation schema and field layout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pyarrow as pa

from scripts.cotahist_oracle.errors import OracleMismatch


@dataclass(frozen=True)
class FieldDefinition:
    """Describe one field in the independent COTAHIST layout."""

    name: str
    arrow_type: str
    conversion: str
    start: int | None = None
    stop: int | None = None
    scale: int = 0
    nullable: bool = False


FIELD_DEFINITIONS = (
    FieldDefinition('data_pregao', 'date32[day]', 'date', 2, 10),
    FieldDefinition('codigo_bdi', 'large_string', 'text', 10, 12),
    FieldDefinition('ticker', 'large_string', 'required_text', 12, 24),
    FieldDefinition('tipo_mercado', 'large_string', 'market', 24, 27),
    FieldDefinition('nome_resumido', 'large_string', 'text', 27, 39),
    FieldDefinition('especificacao_papel', 'large_string', 'text', 39, 49),
    FieldDefinition(
        'preco_abertura', 'decimal128(38, 2)', 'decimal', 56, 69, 2
    ),
    FieldDefinition('preco_maximo', 'decimal128(38, 2)', 'decimal', 69, 82, 2),
    FieldDefinition('preco_minimo', 'decimal128(38, 2)', 'decimal', 82, 95, 2),
    FieldDefinition('preco_medio', 'decimal128(38, 2)', 'decimal', 95, 108, 2),
    FieldDefinition(
        'preco_fechamento', 'decimal128(38, 2)', 'decimal', 108, 121, 2
    ),
    FieldDefinition(
        'melhor_oferta_compra', 'decimal128(38, 2)', 'decimal', 121, 134, 2
    ),
    FieldDefinition(
        'melhor_oferta_venda', 'decimal128(38, 2)', 'decimal', 134, 147, 2
    ),
    FieldDefinition('numero_negocios', 'int64', 'integer', 147, 152),
    FieldDefinition('quantidade_total', 'int64', 'integer', 152, 170),
    FieldDefinition(
        'volume_total', 'decimal128(38, 2)', 'decimal', 170, 188, 2
    ),
    FieldDefinition(
        'data_vencimento',
        'date32[day]',
        'optional_date',
        202,
        210,
        nullable=True,
    ),
    FieldDefinition('fator_cotacao', 'int64', 'integer', 210, 217),
    FieldDefinition('codigo_isin', 'large_string', 'text', 230, 242),
    FieldDefinition('numero_distribuicao', 'int64', 'integer', 242, 245),
    FieldDefinition('prazo_termo', 'large_string', 'text', 49, 52),
    FieldDefinition('moeda_referencia', 'large_string', 'text', 52, 56),
    FieldDefinition(
        'preco_exercicio', 'decimal128(38, 2)', 'decimal', 188, 201, 2
    ),
    FieldDefinition(
        'indicador_correcao', 'large_string', 'numeric_code', 201, 202
    ),
    FieldDefinition(
        'preco_exercicio_pontos', 'decimal128(38, 6)', 'decimal', 217, 230, 6
    ),
    FieldDefinition('tipo_registro', 'large_string', 'record_type', 0, 2),
    FieldDefinition('id_fonte', 'large_string', 'source_hash'),
    FieldDefinition('arquivo_origem', 'large_string', 'source_name'),
    FieldDefinition('membro_origem', 'large_string', 'member_name'),
    FieldDefinition('ano_origem', 'int64', 'source_year'),
    FieldDefinition('linha_origem', 'int64', 'source_line'),
    FieldDefinition('registro_original', 'fixed_size_binary[245]', 'original'),
)

COLUMN_NAMES = tuple(field.name for field in FIELD_DEFINITIONS)

OLD_COLUMNS = COLUMN_NAMES[:20]


def independent_schema() -> pa.Schema:
    """Construct the expected Arrow schema from this oracle's own contract."""
    types = {
        'large_string': pa.large_string(),
        'date32[day]': pa.date32(),
        'int64': pa.int64(),
        'fixed_size_binary[245]': pa.binary(245),
    }
    fields = [
        pa.field(
            definition.name,
            pa.decimal128(38, definition.scale)
            if definition.conversion == 'decimal'
            else types[definition.arrow_type],
            nullable=definition.nullable,
        )
        for definition in FIELD_DEFINITIONS
    ]
    return pa.schema(fields)


def validate_schema(actual: pa.Schema) -> None:
    """Require a Parquet schema to match the independent v2 schema."""
    expected = independent_schema()
    actual_fields = [
        (field.name, str(field.type), field.nullable) for field in actual
    ]
    expected_fields = [
        (field.name, str(field.type), field.nullable) for field in expected
    ]
    if actual_fields != expected_fields:
        raise OracleMismatch(
            f'v2 schema differs from the independent contract: '
            f'{actual_fields!r}'
        )
    if b'pandas' in (actual.metadata or {}):
        raise OracleMismatch('pandas metadata is not part of the v2 contract')


def schema_fingerprint(schema: pa.Schema) -> str:
    """Compute the stable logical fingerprint for a schema."""
    contract = [
        {
            'name': field.name,
            'type': str(field.type),
            'nullable': field.nullable,
        }
        for field in schema
    ]
    encoded = json.dumps(
        contract, ensure_ascii=False, separators=(',', ':')
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
