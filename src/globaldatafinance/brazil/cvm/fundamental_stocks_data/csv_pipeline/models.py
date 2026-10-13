"""Typed facts produced while validating one CVM CSV member."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyarrow import Schema


@dataclass(frozen=True)
class EncodingPlan:
    """The strict decoding decision for one reopenable CVM CSV member."""

    encoding: str
    has_utf8_bom: bool
    needs_utf8_spool: bool
    source_member: str


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
    """Validated structure, complete content digest, and source bounds."""

    header: tuple[str, ...]
    rows: int
    content_sha256: str
    max_record_bytes: int
    normalized_path: Path | None = None
    short_rows_seen: bool = False
    physical_lines: int = 0
