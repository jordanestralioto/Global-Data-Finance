"""Typed facts produced while analysing one CVM CSV member."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import FLOAT, INTEGER, NULL_TOKENS

if TYPE_CHECKING:
    from pyarrow import Schema


_MAX_INT64_TEXT = str(2**63 - 1)
_MIN_INT64_MAGNITUDE_TEXT = str(2**63)
_MAX_UINT64_TEXT = str(2**64 - 1)


@dataclass(frozen=True)
class EncodingPlan:
    """The strict decoding decision for one reopenable CVM CSV member."""

    encoding: str
    has_utf8_bom: bool
    needs_utf8_spool: bool
    source_member: str


@dataclass
class ColumnInference:
    """Global observations used to choose one persisted Arrow type."""

    has_non_null: bool = False
    has_null: bool = False
    has_signed_integer: bool = False
    has_unsigned_integer: bool = False
    has_float: bool = False
    has_boolean: bool = False
    has_string: bool = False
    has_signed_overflow: bool = False
    has_unsigned_overflow: bool = False

    def observe(self, value: str) -> None:
        """Classify one raw non-header CSV value without coercing it."""
        if value in NULL_TOKENS:
            self.has_null = True
            return
        self.has_non_null = True
        if value.casefold() in {'true', 'false'}:
            self.has_boolean = True
            return
        if INTEGER.fullmatch(value):
            self._observe_integer(value)
            return
        if FLOAT.fullmatch(value) and math.isfinite(float(value)):
            self.has_float = True
            return
        self.has_string = True

    def _observe_integer(self, value: str) -> None:
        """Classify arbitrary-width integer text without numeric parsing."""
        negative = value.startswith('-')
        magnitude = value.lstrip('-').lstrip('0') or '0'
        if negative:
            if _greater_than(magnitude, _MIN_INT64_MAGNITUDE_TEXT):
                self.has_signed_overflow = True
            else:
                self.has_signed_integer = True
            return
        if _greater_than(magnitude, _MAX_UINT64_TEXT):
            self.has_unsigned_overflow = True
        elif _greater_than(magnitude, _MAX_INT64_TEXT):
            self.has_unsigned_integer = True
        else:
            self.has_signed_integer = True


def _greater_than(value: str, limit: str) -> bool:
    """Compare normalized non-negative integer text without coercion."""
    return len(value) > len(limit) or (
        len(value) == len(limit) and value > limit
    )


@dataclass(frozen=True)
class CsvPipelineResult:
    """Validated staged CVM artifact facts for transactional publication."""

    rows: int
    schema_fingerprint: str
    schema: Schema
    header: tuple[str, ...]
    row_groups: tuple[int, ...]


@dataclass
class CsvAnalysis:
    """The header, global inference, and normalized source location."""

    header: tuple[str, ...]
    columns: list[ColumnInference]
    rows: int
    normalized_path: Path | None = None
    short_rows_seen: bool = False
    physical_lines: int = 0
