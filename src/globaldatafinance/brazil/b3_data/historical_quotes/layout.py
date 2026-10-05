"""Canonical source and logical layout for B3 COTAHIST quotation rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConversionKind = Literal[
    'date',
    'string',
    'required_text',
    'market_code',
    'numeric_code',
    'decimal',
    'integer',
    'optional_date',
    'record_type',
    'sha256',
    'source_filename',
    'source_member',
    'source_year',
    'source_line',
    'original_record',
]


@dataclass(frozen=True)
class B3FieldDefinition:
    """Describe one logical value and its source conversion contract."""

    name: str
    kind: ConversionKind
    start: int | None = None
    stop: int | None = None
    scale: int | None = None
    nullable: bool = False
    trim: bool = True


B3_LAYOUT_VERSION = 2
B3_QUOTATION_WIDTH = 245

B3_QUOTATION_LAYOUT = (
    B3FieldDefinition('data_pregao', 'date', 2, 10),
    B3FieldDefinition('codigo_bdi', 'string', 10, 12),
    B3FieldDefinition('ticker', 'required_text', 12, 24),
    B3FieldDefinition('tipo_mercado', 'market_code', 24, 27, trim=False),
    B3FieldDefinition('nome_resumido', 'string', 27, 39),
    B3FieldDefinition('especificacao_papel', 'string', 39, 49),
    B3FieldDefinition('preco_abertura', 'decimal', 56, 69, scale=2),
    B3FieldDefinition('preco_maximo', 'decimal', 69, 82, scale=2),
    B3FieldDefinition('preco_minimo', 'decimal', 82, 95, scale=2),
    B3FieldDefinition('preco_medio', 'decimal', 95, 108, scale=2),
    B3FieldDefinition('preco_fechamento', 'decimal', 108, 121, scale=2),
    B3FieldDefinition('melhor_oferta_compra', 'decimal', 121, 134, scale=2),
    B3FieldDefinition('melhor_oferta_venda', 'decimal', 134, 147, scale=2),
    B3FieldDefinition('numero_negocios', 'integer', 147, 152),
    B3FieldDefinition('quantidade_total', 'integer', 152, 170),
    B3FieldDefinition('volume_total', 'decimal', 170, 188, scale=2),
    B3FieldDefinition(
        'data_vencimento', 'optional_date', 202, 210, nullable=True
    ),
    B3FieldDefinition('fator_cotacao', 'integer', 210, 217),
    B3FieldDefinition('codigo_isin', 'string', 230, 242),
    B3FieldDefinition('numero_distribuicao', 'integer', 242, 245),
    B3FieldDefinition('prazo_termo', 'string', 49, 52),
    B3FieldDefinition('moeda_referencia', 'string', 52, 56),
    B3FieldDefinition('preco_exercicio', 'decimal', 188, 201, scale=2),
    B3FieldDefinition('indicador_correcao', 'numeric_code', 201, 202),
    B3FieldDefinition('preco_exercicio_pontos', 'decimal', 217, 230, scale=6),
    B3FieldDefinition('tipo_registro', 'record_type', 0, 2),
    B3FieldDefinition('id_fonte', 'sha256'),
    B3FieldDefinition('arquivo_origem', 'source_filename'),
    B3FieldDefinition('membro_origem', 'source_member'),
    B3FieldDefinition('ano_origem', 'source_year'),
    B3FieldDefinition('linha_origem', 'source_line'),
    B3FieldDefinition('registro_original', 'original_record', 0, 245),
)

B3_FIELD_NAMES = tuple(field.name for field in B3_QUOTATION_LAYOUT)
B3_FIELDS_BY_NAME = {field.name: field for field in B3_QUOTATION_LAYOUT}

if len(B3_FIELD_NAMES) != 32 or len(set(B3_FIELD_NAMES)) != 32:
    raise RuntimeError('The canonical B3 schema must contain 32 unique fields')
