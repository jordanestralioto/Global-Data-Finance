"""Bounded physical records and exact QUOTE_NONE content fingerprints."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TextIO

from .....macro_exceptions import ExtractionError
from .constants import MAX_COLUMNS, MAX_RECORD_BYTES


def read_records(text: TextIO, source: str) -> Iterator[list[str]]:
    """Split only semicolons and physical CR/LF records within byte limits."""
    line_number = 0
    while line := text.readline(MAX_RECORD_BYTES + 1):
        line_number += 1
        if len(line.encode('utf-8')) > MAX_RECORD_BYTES:
            raise ExtractionError(
                source,
                f'CSV record exceeds {MAX_RECORD_BYTES} UTF-8 bytes; '
                f'line={line_number}',
            )
        if line.count(';') >= MAX_COLUMNS:
            raise ExtractionError(
                source,
                f'CSV record exceeds {MAX_COLUMNS} columns; '
                f'line={line_number}',
            )
        if line.endswith('\r\n'):
            line = line[:-2]
        elif line.endswith(('\r', '\n')):
            line = line[:-1]
        yield line.split(';')
