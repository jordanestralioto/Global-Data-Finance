"""Canonical ordered digest for B3 logical quotation rows."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Sequence
from typing import Protocol

from .layout import B3_FIELD_NAMES, B3_LAYOUT_VERSION


class _HashDigest(Protocol):
    """Minimal digest surface used for testable canonical framing."""

    def update(self, data: bytes, /) -> None: ...

    def hexdigest(self) -> str: ...


class B3OrderedRowDigest:
    """Hash schema-ordered values with explicit types and length framing."""

    def __init__(self) -> None:
        """Initialize a SHA-256 stream with the versioned logical layout."""
        self._digest: _HashDigest = hashlib.sha256()
        self._digest.update(b'GLOBALDATAFINANCE-B3-ROW-DIGEST\x00')
        self._digest.update(B3_LAYOUT_VERSION.to_bytes(4, 'big'))
        self._digest.update(len(B3_FIELD_NAMES).to_bytes(2, 'big'))
        for name in B3_FIELD_NAMES:
            _update_frame(self._digest, b'N', name.encode('utf-8'))
        self.rows = 0

    def update(self, row: Sequence[str | bytes | None]) -> None:
        """Append one row while preserving order and duplicate occurrences."""
        if len(row) != len(B3_FIELD_NAMES):
            raise ValueError(
                f'B3 digest row width must be {len(B3_FIELD_NAMES)}'
            )
        self._digest.update(b'R')
        for value in row:
            if value is None:
                self._digest.update(b'Z')
            elif isinstance(value, bytes):
                _update_frame(self._digest, b'B', base64.b64encode(value))
            else:
                _update_frame(self._digest, b'S', value.encode('utf-8'))
        self.rows += 1

    def hexdigest(self) -> str:
        """Return the current lowercase SHA-256 digest."""
        return self._digest.hexdigest()


def _update_frame(digest: _HashDigest, kind: bytes, value: bytes) -> None:
    """Hash one typed payload with an unambiguous 64-bit byte length."""
    digest.update(kind)
    digest.update(len(value).to_bytes(8, 'big'))
    digest.update(value)
