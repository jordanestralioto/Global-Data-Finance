"""Prove Arrow batch conversion preserves every digest payload byte."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pyarrow as pa
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    schema as b3_schema,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    verification as b3_verification,
)
from globaldatafinance.brazil.b3_data.historical_quotes.row_digest import (
    B3OrderedRowDigest,
)

pytestmark = pytest.mark.unit


def _extreme_value(field: pa.Field, row_index: int) -> object:
    """Build exact values at the supported Arrow representation boundaries."""
    if row_index == 2 and field.nullable:
        return None
    if pa.types.is_date32(field.type):
        return (
            date(1, 1, 1),
            date(9999, 12, 31),
            date(2024, 2, 29),
        )[row_index]
    if pa.types.is_decimal(field.type):
        scale = field.type.scale
        if row_index == 0:
            return Decimal('9' * (38 - scale) + '.' + '9' * scale)
        return Decimal('0').quantize(Decimal('1').scaleb(-scale))
    if pa.types.is_integer(field.type):
        return (2**63 - 1, -(2**63), 0)[row_index]
    if pa.types.is_fixed_size_binary(field.type):
        return bytes(range(245))
    return ('ação', '', '0001')[row_index]


def _reference_value(value: object) -> str | bytes | None:
    """Derive the canonical payload independently of Arrow casts."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, int):
        return str(value)
    if value is None or isinstance(value, (str, bytes)):
        return value
    raise TypeError(type(value).__name__)


def test_batch_canonicalization_preserves_exact_extreme_values() -> None:
    """Decimals, ISO dates, Unicode, binary, and null keep their bytes."""
    schema = b3_schema.build_b3_schema()
    records = [
        {field.name: _extreme_value(field, index) for field in schema}
        for index in range(3)
    ]
    batch = pa.RecordBatch.from_pylist(records, schema=schema)
    converted = b3_verification.canonical_columns(batch)
    expected = [
        [_reference_value(record[field.name]) for record in records]
        for field in schema
    ]

    assert [column.to_pylist() for column in converted] == expected
    observed_digest = B3OrderedRowDigest()
    reference_digest = B3OrderedRowDigest()
    observed_digest.update_columns(converted)
    for index in range(batch.num_rows):
        reference_digest.update([column[index] for column in expected])
    assert observed_digest.hexdigest() == reference_digest.hexdigest()
    assert observed_digest.rows == 3
