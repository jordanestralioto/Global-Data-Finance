"""Text normalization and Markdown table primitives for sabatina."""

from __future__ import annotations

import re
import unicodedata

DASHES = '\N{EM DASH}', '\N{EN DASH}'


EMPTY_VALUES = frozenset({'', *DASHES, '-', 'n/a', 'na'})


SUBSECTION_RE = re.compile(r'^###\s+(?:\d+\.\s*)?(.+?)\s*$')


PLACEHOLDER_RE = re.compile(r'<[^<>\n]{3,}>')


TERMINAL_PLACEHOLDER_RE = re.compile(
    r'<[^<>\n]{3,}>|\b(?:tbd|todo|to be decided|fill me)\b',
    re.IGNORECASE,
)


SEPARATOR_CELL_RE = re.compile(r'^:?-{3,}:?$')


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize('NFD', text)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    return _strip_accents(text).strip().lower()


def is_empty(value: str) -> bool:
    return normalize(value) in EMPTY_VALUES


def is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_RE.search(value))


def is_terminal_placeholder(value: str) -> bool:
    return bool(TERMINAL_PLACEHOLDER_RE.search(value))


def split_cells(row: str) -> list[str]:
    """Split cells while preserving pipes inside inline code."""
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for char in row.strip().strip('|'):
        if char == '`':
            in_code = not in_code
        if char == '|' and not in_code:
            cells.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append(''.join(current).strip())
    return cells


def table_rows(body: list[tuple[int, str]]) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    for number, content in body:
        stripped = content.strip()
        if not stripped.startswith('|'):
            continue
        cells = split_cells(stripped)
        if all(SEPARATOR_CELL_RE.match(cell) for cell in cells if cell):
            continue
        rows.append((number, cells))
    return rows


def parse_tables(
    body: list[tuple[int, str]],
) -> list[list[tuple[int, list[str]]]]:
    tables: list[list[tuple[int, list[str]]]] = []
    current: list[tuple[int, list[str]]] = []
    for number, content in body:
        stripped = content.strip()
        if not stripped.startswith('|'):
            if current:
                tables.append(current)
                current = []
            continue
        cells = split_cells(stripped)
        if all(SEPARATOR_CELL_RE.match(cell) for cell in cells if cell):
            continue
        current.append((number, cells))
    if current:
        tables.append(current)
    return tables


def find_table(
    tables: list[list[tuple[int, list[str]]]], marker: str
) -> list[tuple[int, list[str]]] | None:
    for table in tables:
        _, header = table[0]
        if any(marker in normalize(cell) for cell in header):
            return table
    return None
