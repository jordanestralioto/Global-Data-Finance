"""Canonical CVM record fingerprints shared by input and output validation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyarrow import RecordBatch

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

    def update_batch(self, batch: RecordBatch) -> None:
        """Hash a bounded text batch without creating Python field objects."""
        import pyarrow as pa
        import pyarrow.compute as pc

        if any(column.null_count for column in batch.columns):
            raise ValueError('Exact-text CVM Parquet contains nulls')
        joined = pc.binary_join_element_wise(*batch.columns, ';')
        rows = pc.binary_join_element_wise(joined, '\n', '')
        _, offsets, payload = rows.buffers()
        positions = pa.Array.from_buffers(
            pa.int32(), len(rows) + 1, [None, offsets], offset=rows.offset
        )
        start, end = positions[0].as_py(), positions[-1].as_py()
        self._digest.update(memoryview(payload)[start:end])

    def hexdigest(self) -> str:
        """Return the fingerprint of the header and all observed records."""
        return self._digest.hexdigest()
