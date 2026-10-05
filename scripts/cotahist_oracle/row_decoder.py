"""Decode fixed-width COTAHIST records independently of production code."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from scripts.cotahist_oracle.errors import OracleMismatch
from scripts.cotahist_oracle.schema import FIELD_DEFINITIONS, FieldDefinition
from scripts.cotahist_oracle.source_reader import require_ascii_digits


def decode_quote(
    record: bytes,
    *,
    source_name: str,
    member: str,
    year: int,
    line_number: int,
    content_sha256: str,
) -> dict[str, Any]:
    """Decode a row using the independent fixed-width field map."""
    result: dict[str, Any] = {}
    for definition in FIELD_DEFINITIONS:
        kind = definition.conversion
        if kind == 'source_hash':
            value: Any = content_sha256
        elif kind == 'source_name':
            value = source_name
        elif kind == 'member_name':
            value = member
        elif kind == 'source_year':
            value = year
        elif kind == 'source_line':
            value = line_number
        elif kind == 'original':
            value = record
        else:
            if definition.start is None or definition.stop is None:
                raise RuntimeError(
                    f'missing independent offsets: {definition.name}'
                )
            raw = record[definition.start : definition.stop]
            value = decode_field(
                definition, raw, year, source_name, line_number
            )
        result[definition.name] = value
    return result


def decode_field(
    definition: FieldDefinition,
    raw: bytes,
    year: int,
    source_name: str,
    line_number: int,
) -> Any:
    """Decode and validate one field from a fixed-width record."""
    text = raw.decode('latin-1')
    value = (
        text
        if definition.conversion in {'decimal', 'integer', 'numeric_code'}
        else text.strip(' ')
    )
    label = f'{source_name}: line {line_number} field {definition.name}'
    decoder = _FIELD_DECODERS.get(definition.conversion)
    if decoder is None:
        raise RuntimeError(
            f'unsupported oracle conversion: {definition.conversion}'
        )
    return decoder(definition, raw, value, year, label)


def _decode_record_type(
    _definition: FieldDefinition,
    raw: bytes,
    _value: str,
    _year: int,
    label: str,
) -> str:
    if raw != b'01':
        raise OracleMismatch(f'{label} is not type 01')
    return '01'


def _decode_date(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    year: int,
    label: str,
) -> date:
    parsed = _parse_field_date(value, label)
    if parsed.year != year:
        raise OracleMismatch(f'{label} is outside source year {year}')
    return parsed


def _decode_optional_date(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> date | None:
    if value in {'', '00000000'}:
        return None
    return _parse_field_date(value, label)


def _decode_decimal(
    definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> Decimal:
    require_ascii_digits(value.encode('latin-1'), label)
    digits = value.lstrip('0') or '0'
    if definition.scale:
        digits = digits.zfill(definition.scale + 1)
        return Decimal(
            f'{digits[: -definition.scale]}.{digits[-definition.scale :]}'
        )
    return Decimal(digits)


def _decode_integer(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> int:
    require_ascii_digits(value.encode('latin-1'), label)
    return int(value)


def _decode_market(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> str:
    if len(value) != 3 or not value.isascii() or not value.isdecimal():
        raise OracleMismatch(f'{label} is not three ASCII digits')
    return value


def _decode_numeric_code(
    _definition: FieldDefinition,
    raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> str:
    require_ascii_digits(raw, label)
    return value


def _decode_required_text(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    label: str,
) -> str:
    if not value:
        raise OracleMismatch(f'{label} is empty')
    return value


def _decode_text(
    _definition: FieldDefinition,
    _raw: bytes,
    value: str,
    _year: int,
    _label: str,
) -> str:
    return value


_FIELD_DECODERS: dict[
    str,
    Callable[[FieldDefinition, bytes, str, int, str], Any],
] = {
    'record_type': _decode_record_type,
    'date': _decode_date,
    'optional_date': _decode_optional_date,
    'decimal': _decode_decimal,
    'integer': _decode_integer,
    'market': _decode_market,
    'numeric_code': _decode_numeric_code,
    'required_text': _decode_required_text,
    'text': _decode_text,
}


def _parse_field_date(value: str, label: str) -> date:
    if len(value) != 8 or not value.isascii() or not value.isdecimal():
        raise OracleMismatch(f'{label} must contain eight ASCII digits')
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as error:
        raise OracleMismatch(f'{label} is not a valid date') from error
