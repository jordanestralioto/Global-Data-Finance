"""Independently encode the documented version 2 ordered row digest."""

from __future__ import annotations

import base64
import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

from scripts.cotahist_oracle.schema import COLUMN_NAMES


def new_rows_digest() -> Any:
    """Start the versioned SHA-256 stream in independent schema order."""
    digest = hashlib.sha256()
    digest.update(b'GLOBALDATAFINANCE-B3-ROW-DIGEST\x00')
    digest.update((2).to_bytes(4, 'big'))
    digest.update(len(COLUMN_NAMES).to_bytes(2, 'big'))
    for name in COLUMN_NAMES:
        _frame(digest, b'N', name.encode('utf-8'))
    return digest


def update_rows_digest(digest: Any, row: dict[str, Any]) -> None:
    """Frame exact dates, decimals, integers, text, nulls and Base64 bytes."""
    digest.update(b'R')
    for name in COLUMN_NAMES:
        value = row[name]
        if value is None:
            digest.update(b'Z')
        elif isinstance(value, bytes):
            _frame(digest, b'B', base64.b64encode(value))
        else:
            if isinstance(value, date):
                text = value.isoformat()
            elif isinstance(value, Decimal):
                text = format(value, 'f')
            else:
                text = str(value)
            _frame(digest, b'S', text.encode('utf-8'))


def _frame(digest: Any, tag: bytes, payload: bytes) -> None:
    """Append one type tag, unsigned 64-bit byte length, and payload."""
    digest.update(tag + len(payload).to_bytes(8, 'big') + payload)
