"""CVM exact-text contract and bounded CSV processing limits."""

from __future__ import annotations

MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_COLUMNS = 4096
ROW_GROUP_BYTES = 16 * 1024 * 1024
CP1252_UNDEFINED = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})
CP1252_DEFINED_RANGE = frozenset(range(0x80, 0xA0)) - CP1252_UNDEFINED
ROW_GROUP_SIZE = 50_000
