"""Validate COTAHIST header, detail, and trailer records."""

from __future__ import annotations

from datetime import date

from .....macro_exceptions import ExtractionError
from ..integrity import B3RecordContext

HEADER_SIZE = 245


def validate_header(
    record: bytes,
    year: int,
    context: B3RecordContext,
) -> date:
    """Validate the official fixed header identity and reserved area."""
    expected_name = f'COTAHIST.{year:04d}'.encode('ascii')
    _validate_control_identity(record, b'00', expected_name, context)
    if record[31:245] != b' ' * 214:
        raise line_error(
            context,
            'header_reserved',
            record[31:45].decode('latin-1'),
            'Header reserved bytes must be spaces',
        )
    return parse_control_date(record[23:31], context)


def validate_trailer(
    record: bytes,
    year: int,
    header: bytes | None,
    context: B3RecordContext,
) -> int:
    """Validate the official trailer identity, count field, and reserve."""
    expected_name = f'COTAHIST.{year:04d}'.encode('ascii')
    _validate_control_identity(record, b'99', expected_name, context)
    if header is None:
        raise RuntimeError('Trailer validation requires a prior header')
    if record[2:31] != header[2:31]:
        raise line_error(
            context,
            'trailer_identity',
            record[2:31].decode('latin-1'),
            'Header and trailer identity and generation date must agree',
        )
    if record[42:245] != b' ' * 203:
        raise line_error(
            context,
            'trailer_reserved',
            record[42:56].decode('latin-1'),
            'Trailer reserved bytes must be spaces',
        )
    raw_count = record[31:42].decode('latin-1')
    if not ascii_digits(raw_count):
        raise line_error(
            context,
            'declared_records',
            raw_count,
            'Trailer record total must contain eleven ASCII digits',
        )
    return int(raw_count)


def _validate_control_identity(
    record: bytes,
    expected_type: bytes,
    expected_name: bytes,
    context: B3RecordContext,
) -> None:
    """Validate record type, file identifier, and BOVESPA origin."""
    if record[:2] != expected_type:
        raise line_error(
            context,
            'record_type',
            record[:2].decode('latin-1'),
            f'Expected control record {expected_type.decode("ascii")}',
        )
    if record[2:15] != expected_name:
        raise line_error(
            context,
            'control_filename',
            record[2:15].decode('latin-1'),
            f'Expected control filename {expected_name.decode("ascii")}',
        )
    if record[15:23] != b'BOVESPA ':
        raise line_error(
            context,
            'control_origin',
            record[15:23].decode('latin-1'),
            'Control origin must be BOVESPA',
        )


def parse_control_date(raw_value: bytes, context: B3RecordContext) -> date:
    """Parse the eight ASCII generation-date digits from a control record."""
    value = raw_value.decode('latin-1')
    if len(value) != 8 or not ascii_digits(value):
        raise line_error(
            context,
            'generation_date',
            value,
            'Generation date must contain eight ASCII digits',
        )
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as error:
        raise line_error(
            context,
            'generation_date',
            value,
            error,
        ) from error


def trailer_convention(declared: int, quotations: int) -> str | None:
    """Accept the two observed count conventions exactly."""
    if declared == quotations + 2:
        return 'quotes_and_controls'
    if declared == quotations:
        return 'quotes_only'
    return None


def line_error(
    context: B3RecordContext,
    field_name: str,
    raw_value: str,
    cause: Exception | str,
) -> ExtractionError:
    """Create a bounded field-level source diagnostic."""
    return context.with_field(field_name, raw_value).extraction_error(cause)


def ascii_digits(value: str) -> bool:
    """Return whether a string contains only ASCII digits."""
    return value.isascii() and value.isdecimal()
