"""Convert canonical B3 fields and materialize typed quotation rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

from .....macro_exceptions import ExtractionError
from ..integrity import B3RecordContext
from ..layout import B3_QUOTATION_LAYOUT, B3FieldDefinition


def field_value(
    definition: B3FieldDefinition,
    line: str,
    original_record: bytes,
    context: B3RecordContext,
    source_year: int | None,
    source_sha256: str,
) -> CsvValue:
    """Convert one canonical field using its source-owned definition."""
    if definition.kind in {
        'sha256',
        'source_filename',
        'source_member',
        'source_year',
        'source_line',
        'original_record',
    }:
        return provenance_value(
            definition,
            context,
            source_year,
            source_sha256,
            original_record,
        )
    field_text = slice_field(definition, line)
    return convert_field_value(definition, field_text, context)


def provenance_value(
    definition: B3FieldDefinition,
    context: B3RecordContext,
    source_year: int | None,
    source_sha256: str,
    original_record: bytes,
) -> CsvValue:
    """Return the validated source identity for one provenance field."""
    if definition.kind == 'sha256':
        return source_sha256
    if definition.kind == 'source_filename':
        return context.source_basename
    if definition.kind == 'source_member':
        return context.zip_member
    if definition.kind == 'source_year':
        return str(source_year or 0)
    if definition.kind == 'source_line':
        return str(context.physical_line)
    if definition.kind == 'original_record':
        return original_record
    raise RuntimeError(f'Unsupported B3 provenance kind: {definition.kind}')


def convert_field_value(
    definition: B3FieldDefinition,
    raw_value: str,
    context: B3RecordContext,
) -> CsvValue:
    """Convert a raw quotation field to its canonical CSV value."""
    if definition.kind == 'record_type':
        return raw_value
    if definition.kind == 'date':
        return normalize_required_date(
            raw_value, context, field_name=definition.name
        )
    if definition.kind == 'optional_date':
        return normalize_optional_date(
            raw_value, context, field_name=definition.name
        )
    if definition.kind in {'decimal', 'integer'}:
        return numeric_value(definition, raw_value, context)
    if definition.kind == 'required_text':
        return normalize_required_text(
            raw_value, context, field_name=definition.name
        )
    if definition.kind in {'market_code', 'numeric_code'}:
        return normalize_numeric_code(definition, raw_value, context)
    if definition.kind == 'string':
        return raw_value.strip(' ') if definition.trim else raw_value
    raise RuntimeError(f'Unsupported B3 conversion kind: {definition.kind}')


def normalize_numeric_code(
    definition: B3FieldDefinition,
    raw_value: str,
    context: B3RecordContext,
) -> str:
    """Validate digit codes while preserving their source representation."""
    if not is_ascii_digits(raw_value) or (
        definition.kind == 'market_code' and len(raw_value) != 3
    ):
        cause = (
            'TPMERC must contain exactly three ASCII digits'
            if definition.kind == 'market_code'
            else 'Numeric code must contain ASCII digits'
        )
        raise field_error(context, definition.name, raw_value, cause)
    return raw_value


def numeric_value(
    definition: B3FieldDefinition,
    raw_value: str,
    context: B3RecordContext,
) -> str:
    """Normalize one integral or fixed-scale decimal field."""
    if definition.kind == 'integer':
        return normalize_int(raw_value, context, field_name=definition.name)
    if definition.scale is None:
        raise RuntimeError(f'Missing decimal scale for {definition.name}')
    return normalize_decimal(
        raw_value,
        definition.scale,
        context,
        field_name=definition.name,
    )


def slice_field(definition: B3FieldDefinition, line: str) -> str:
    """Extract one field using its validated fixed-width offsets."""
    if definition.start is None or definition.stop is None:
        raise RuntimeError(f'Missing source offsets for {definition.name}')
    return line[definition.start : definition.stop]


def typed_record(row: CsvRow) -> dict[str, Any]:
    """Materialize typed Python values from canonical normalized values."""
    if len(row) != len(B3_QUOTATION_LAYOUT):
        raise ValueError('Canonical B3 row has an incompatible width')
    values: dict[str, Any] = {}
    for definition, value in zip(B3_QUOTATION_LAYOUT, row, strict=True):
        if definition.kind in {'date', 'optional_date'}:
            values[definition.name] = (
                date.fromisoformat(cast(str, value))
                if value is not None
                else None
            )
        elif definition.kind == 'decimal':
            values[definition.name] = Decimal(cast(str, value))
        elif definition.kind in {'integer', 'source_year', 'source_line'}:
            values[definition.name] = int(cast(str, value))
        else:
            values[definition.name] = value
    return values


def field_error(
    context: B3RecordContext | None,
    field_name: str,
    raw_value: str,
    cause: Exception | str,
) -> ExtractionError:
    """Build field context only for a rejected value."""
    if context is None:
        context = B3RecordContext('<memory>', '', 0, 0)
    return context.with_field(field_name, raw_value).extraction_error(cause)


def normalize_required_date(
    raw_value: str,
    context: B3RecordContext | None = None,
    *,
    field_name: str = 'data_pregao',
) -> str:
    """Validate a required date and return ISO format."""
    value = raw_value.strip(' ')
    if len(value) != 8 or not is_ascii_digits(value) or value == '00000000':
        raise field_error(
            context,
            field_name,
            raw_value,
            'Required date is invalid or empty',
        )
    try:
        date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as error:
        raise field_error(context, field_name, raw_value, error) from error
    return f'{value[:4]}-{value[4:6]}-{value[6:]}'


def normalize_optional_date(
    raw_value: str,
    context: B3RecordContext | None = None,
    *,
    field_name: str = 'data_vencimento',
) -> str | None:
    """Accept only blank or zero sentinels as absent expiration dates."""
    value = raw_value.strip(' ')
    if not value or value == '00000000':
        return None
    if len(value) != 8 or not is_ascii_digits(value):
        raise field_error(
            context,
            field_name,
            raw_value,
            'Optional date is invalid',
        )
    try:
        date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as error:
        raise field_error(context, field_name, raw_value, error) from error
    return f'{value[:4]}-{value[4:6]}-{value[6:]}'


def normalize_decimal(
    raw_value: str,
    scale: int,
    context: B3RecordContext | None = None,
    *,
    field_name: str = 'decimal',
) -> str:
    """Normalize an implied-decimal source field without floating point."""
    value = raw_value
    if not value or not is_ascii_digits(value):
        raise field_error(
            context,
            field_name,
            raw_value,
            'Required implied-decimal field is empty or non-numeric',
        )
    max_integer_digits = 38 - scale
    normalized = value.lstrip('0') or '0'
    if len(normalized) > max_integer_digits:
        raise field_error(
            context,
            field_name,
            raw_value,
            f'Value exceeds decimal128(38, {scale})',
        )
    padded = normalized.zfill(scale + 1)
    return f'{padded[:-scale]}.{padded[-scale:]}'


def normalize_int(
    raw_value: str,
    context: B3RecordContext | None = None,
    *,
    field_name: str = 'integer',
) -> str:
    """Validate an int64 field without parsing invalid input first."""
    value = raw_value
    if not value or not is_ascii_digits(value):
        raise field_error(
            context,
            field_name,
            raw_value,
            'Required integer is empty or non-numeric',
        )
    normalized = value.lstrip('0') or '0'
    if len(normalized) > len(MAX_INT64_TEXT) or (
        len(normalized) == len(MAX_INT64_TEXT) and normalized > MAX_INT64_TEXT
    ):
        raise field_error(
            context, field_name, raw_value, 'Integer exceeds int64'
        )
    return normalized


def normalize_required_text(
    raw_value: str,
    context: B3RecordContext | None = None,
    *,
    field_name: str,
) -> str:
    """Strip a required text field while rejecting an empty value."""
    value = raw_value.strip(' ')
    if not value:
        raise field_error(
            context,
            field_name,
            raw_value,
            'Required text field is empty',
        )
    return value


MAX_INT64_TEXT = str(2**63 - 1)

CsvValue = str | bytes | None

CsvRow = tuple[CsvValue, ...]


def is_ascii_digits(value: str) -> bool:
    """Accept only decimal ASCII digits in fixed-width numeric fields."""
    return value.isascii() and value.isdecimal()
