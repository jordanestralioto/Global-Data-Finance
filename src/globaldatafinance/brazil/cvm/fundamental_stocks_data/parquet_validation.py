"""Bounded validation of every persisted CVM Parquet data page."""

from __future__ import annotations

from typing import Any

from .content_fingerprint import RecordDigest

_VALIDATION_BATCH_SIZE = 8_192


def validate_parquet_data(
    parquet: Any,
    expected_rows: int,
    *,
    expected_content_sha256: str | None = None,
) -> None:
    """Read every page and verify count and any exact-text fingerprint."""
    metadata = parquet.schema_arrow.metadata or {}
    if expected_content_sha256 is None:
        stored_digest = metadata.get(b'cvm.content-sha256')
        if stored_digest is not None:
            expected_content_sha256 = stored_digest.decode('ascii')
    digest = (
        RecordDigest(parquet.schema_arrow.names)
        if expected_content_sha256 is not None
        else None
    )
    read_rows = 0
    group_rows = [
        parquet.metadata.row_group(index).num_rows
        for index in range(parquet.metadata.num_row_groups)
    ]
    batch_size = min(
        _VALIDATION_BATCH_SIZE, max(1, max(group_rows, default=1))
    )
    for batch in parquet.iter_batches(
        batch_size=batch_size, use_threads=False
    ):
        batch.validate(full=True)
        if digest is not None:
            digest.update_batch(batch)
        read_rows += batch.num_rows
    if read_rows != expected_rows:
        raise ValueError(
            'Parquet data row count validation failed: '
            f'expected {expected_rows}, read {read_rows}'
        )
    if digest is not None and digest.hexdigest() != expected_content_sha256:
        raise ValueError(
            'Parquet content differs from the complete CSV source'
        )
