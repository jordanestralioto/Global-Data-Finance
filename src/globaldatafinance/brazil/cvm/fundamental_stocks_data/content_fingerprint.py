"""Canonical CVM record fingerprints shared by input and output validation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

CONTRACT_VERSION = b'exact-text-v1'


class RecordDigest:
    """Hash unambiguous normalized records independently of batch sizes."""

    def __init__(self, header: Sequence[str]) -> None:
        """Bind the digest to the contract and ordered header."""
        self._digest = hashlib.sha256(CONTRACT_VERSION + b'\x00')
        self.update(header)

    def update(self, row: Sequence[str]) -> None:
        """Add one decoded record, preserving every field character."""
        self._digest.update((';'.join(row) + '\n').encode('utf-8'))

    def hexdigest(self) -> str:
        """Return the fingerprint of the header and all observed records."""
        return self._digest.hexdigest()
