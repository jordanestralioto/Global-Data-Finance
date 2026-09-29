"""Contextual integrity diagnostics for B2 COTAHIST records."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from ....macro_exceptions import ExtractionError

COTAHIST_RECORD_WIDTH = 245
_COTAHIST_MAX_PHYSICAL_LINE_CONTENT_BYTES = COTAHIST_RECORD_WIDTH + 2
_COTAHIST_MAX_LINE_ENDING_BYTES = 2
_COTAHIST_MAX_PHYSICAL_LINE_BYTES = (
    _COTAHIST_MAX_PHYSICAL_LINE_CONTENT_BYTES + _COTAHIST_MAX_LINE_ENDING_BYTES
)


class CotahistLineTooLongError(ValueError):
    """Indicate that a physical COTAHIST line exceeds its byte limit."""


class BoundedLineSource(Protocol):
    """Provide bounded binary lines from files and ZIP members."""

    def readline(self, size: int = -1, /) -> bytes:
        """Read no more than ``size`` bytes from the source."""
        ...


def iter_bounded_cotahist_lines(
    source: BoundedLineSource,
) -> Iterator[tuple[int, bytes]]:
    """Read physical records with a byte cap before callers decode them."""
    line_number = 0
    while raw_line := source.readline(_COTAHIST_MAX_PHYSICAL_LINE_BYTES + 1):
        line_number += 1
        content = raw_line.removesuffix(b'\r\n').removesuffix(b'\n')
        content = content.removesuffix(b'\r')
        if (
            len(raw_line) > _COTAHIST_MAX_PHYSICAL_LINE_BYTES
            or len(content) > _COTAHIST_MAX_PHYSICAL_LINE_CONTENT_BYTES
        ):
            raise CotahistLineTooLongError(
                f'physical line {line_number} exceeds the COTAHIST '
                'physical-line limit of '
                f'{_COTAHIST_MAX_PHYSICAL_LINE_CONTENT_BYTES} content bytes'
            )
        yield line_number, raw_line


@dataclass(frozen=True)
class B3RecordContext:
    """Locate one B3 record without exposing an unbounded source line."""

    source_basename: str
    zip_member: str
    physical_line: int
    logical_record: int
    record_type: str = ''
    field_name: str = ''
    raw_preview: str = ''

    def with_field(self, field_name: str, raw_value: str) -> B3RecordContext:
        """Return a field-specific context with a safe bounded preview."""
        preview = raw_value.replace('\r', '\\r').replace('\n', '\\n')[:80]
        return B3RecordContext(
            source_basename=self.source_basename,
            zip_member=self.zip_member,
            physical_line=self.physical_line,
            logical_record=self.logical_record,
            record_type=self.record_type,
            field_name=field_name,
            raw_preview=preview,
        )

    def extraction_error(self, cause: Exception | str) -> ExtractionError:
        """Build the public error with every available integrity coordinate."""
        cause_text = (
            str(cause)
            if isinstance(cause, str)
            else f'{type(cause).__name__}: {cause}'
        )
        return ExtractionError(
            self.source_basename,
            'source='
            f'{self.source_basename}; member={self.zip_member}; '
            f'record={self.logical_record}; line={self.physical_line}; '
            f'field={self.field_name or "record"}; '
            f'value={self.raw_preview!r}; cause={cause_text}',
        )
