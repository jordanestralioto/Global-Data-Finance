"""Contextual integrity diagnostics for B2 COTAHIST records."""

from __future__ import annotations

from dataclasses import dataclass

from ....macro_exceptions import ExtractionError


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
