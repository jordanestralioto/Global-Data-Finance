"""Lazy construction of the versioned B3 Arrow schema."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from ..layout import B3_FIELD_NAMES, B3_LAYOUT_VERSION, B3_QUOTATION_LAYOUT

if TYPE_CHECKING:
    from pyarrow import Schema

B3_SCHEMA_VERSION = B3_LAYOUT_VERSION
B3_COLUMNS = B3_FIELD_NAMES
B3_STRING_COLUMNS = tuple(
    field.name
    for field in B3_QUOTATION_LAYOUT
    if field.kind
    in {
        'string',
        'required_text',
        'market_code',
        'numeric_code',
        'record_type',
        'sha256',
        'source_filename',
        'source_member',
    }
)
B3_DECIMAL_COLUMNS = tuple(
    field.name for field in B3_QUOTATION_LAYOUT if field.kind == 'decimal'
)
B3_INT_COLUMNS = tuple(
    field.name
    for field in B3_QUOTATION_LAYOUT
    if field.kind in {'integer', 'source_year', 'source_line'}
)
B3_DATE_COLUMNS = tuple(
    field.name
    for field in B3_QUOTATION_LAYOUT
    if field.kind in {'date', 'optional_date'}
)


def build_b3_schema(
    metadata: dict[bytes, bytes] | None = None,
) -> Schema:
    """Build the 32-column logical schema without eager Arrow imports."""
    import pyarrow as pa

    fields = []
    for definition in B3_QUOTATION_LAYOUT:
        if definition.kind in {
            'string',
            'required_text',
            'market_code',
            'numeric_code',
            'record_type',
            'sha256',
            'source_filename',
            'source_member',
        }:
            data_type = pa.large_string()
        elif definition.kind in {'date', 'optional_date'}:
            data_type = pa.date32()
        elif definition.kind == 'decimal':
            if definition.scale is None:
                raise RuntimeError(
                    f'Missing decimal scale for {definition.name}'
                )
            data_type = pa.decimal128(38, definition.scale)
        elif definition.kind in {'integer', 'source_year', 'source_line'}:
            data_type = pa.int64()
        elif definition.kind == 'original_record':
            data_type = pa.binary(245)
        else:
            raise RuntimeError(
                f'Unsupported canonical B3 field kind: {definition.kind}'
            )
        fields.append(
            pa.field(
                definition.name,
                data_type,
                nullable=definition.nullable,
            )
        )
    return pa.schema(fields, metadata=metadata)


def schema_fingerprint(schema: Schema) -> str:
    """Hash field names, order, logical types, and nullability only."""
    contract = [
        {
            'name': field.name,
            'type': str(field.type),
            'nullable': field.nullable,
        }
        for field in schema
    ]
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
