"""Read and validate Parquet artifacts against the independent oracle."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from scripts.cotahist_oracle.errors import OracleMismatch
from scripts.cotahist_oracle.manifest_validation import (
    SCHEMA_FINGERPRINT_KEY,
    SCHEMA_VERSION_KEY,
    read_manifest,
    validate_manifest_identity,
)
from scripts.cotahist_oracle.schema import (
    COLUMN_NAMES,
    independent_schema,
    schema_fingerprint,
    validate_schema,
)
from scripts.cotahist_oracle.source_reader import SourceFacts


def open_oracle_parquet(
    output_path: Path, source_facts: Sequence[SourceFacts]
) -> tuple[pq.ParquetFile, dict[str, Any]]:
    """Open and validate a Parquet artifact against source evidence."""
    parquet = pq.ParquetFile(output_path)
    validate_schema(parquet.schema_arrow)
    manifest = read_manifest(parquet.schema_arrow.metadata or {})
    validate_manifest_identity(manifest, source_facts)
    metadata = parquet.schema_arrow.metadata or {}
    if metadata.get(SCHEMA_VERSION_KEY) != b'2':
        raise OracleMismatch('schema version metadata is not 2')
    expected_fingerprint = schema_fingerprint(independent_schema())
    if metadata.get(SCHEMA_FINGERPRINT_KEY) != expected_fingerprint.encode():
        raise OracleMismatch('logical schema fingerprint differs from oracle')
    return parquet, manifest


def iter_parquet_rows(
    parquet: pq.ParquetFile, batch_size: int
) -> Iterator[dict[str, Any]]:
    """Yield Parquet rows in bounded batches while preserving row order."""
    schema = parquet.schema_arrow
    for batch in parquet.iter_batches(batch_size=batch_size):
        for index, schema_field in enumerate(schema):
            if not schema_field.nullable and batch.column(index).null_count:
                raise OracleMismatch(
                    'non-nullable output field contains nulls: '
                    f'{schema_field.name}'
                )
        columns = [
            batch.column(index).to_pylist()
            for index in range(batch.num_columns)
        ]
        for row_index in range(batch.num_rows):
            yield {
                name: column[row_index]
                for name, column in zip(COLUMN_NAMES, columns, strict=True)
            }
