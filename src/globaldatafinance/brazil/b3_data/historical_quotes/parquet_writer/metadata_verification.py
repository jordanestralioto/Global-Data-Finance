"""Shared metadata checks for private and final B3 Parquet artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....macro_exceptions import ExtractionError
from ..models import ValidatedCotahistSource
from .audit_metadata import (
    B3_AUDIT_METADATA_KEY,
    B3_SCHEMA_FINGERPRINT_METADATA_KEY,
    B3_SCHEMA_VERSION_METADATA_KEY,
)
from .schema import B3_SCHEMA_VERSION, schema_fingerprint

if TYPE_CHECKING:
    from pyarrow import Schema


def open_verified_parquet(
    path: Path,
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...] | None = None,
    manifest_sources: tuple[ValidatedCotahistSource, ...] | None = None,
    *,
    schema_error: str = 'B3 Parquet schema readback failed',
) -> tuple[Any, Schema]:
    """Open an artifact and check its schema and complete expected metadata."""
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    try:
        actual_schema = parquet.schema_arrow
        if not actual_schema.remove_metadata().equals(
            expected_schema.remove_metadata(), check_metadata=True
        ):
            raise ExtractionError(str(path), schema_error)
        metadata = actual_schema.metadata or {}
        if sources is not None:
            _verify_footer_metadata(
                metadata,
                expected_schema,
                sources if manifest_sources is None else manifest_sources,
            )
        elif metadata != (expected_schema.metadata or {}):
            raise ExtractionError(
                str(path), 'Integrity footer metadata differs from preflight'
            )
        if b'pandas' in metadata:
            raise ExtractionError(
                str(path), 'B3 Parquet unexpectedly contains pandas metadata'
            )
        return parquet, actual_schema
    except BaseException:
        parquet.close()
        raise


def verify_row_count(
    path: Path,
    parquet: Any,
    sources: tuple[ValidatedCotahistSource, ...],
) -> int:
    """Require the footer count to match the preflighted selected rows."""
    file_metadata = parquet.metadata
    expected_rows = sum(source.selected_quotes for source in sources)
    if file_metadata is None or file_metadata.num_rows != expected_rows:
        observed = None if file_metadata is None else file_metadata.num_rows
        raise ExtractionError(
            str(path),
            'B3 Parquet row count readback failed: '
            f'expected={expected_rows}; observed={observed}',
        )
    return expected_rows


def _verify_footer_metadata(
    metadata: dict[bytes, bytes],
    expected_schema: Schema,
    sources: tuple[ValidatedCotahistSource, ...],
) -> None:
    """Validate the complete footer against the preflighted run manifest."""
    expected_fingerprint = schema_fingerprint(expected_schema)
    if metadata.get(B3_SCHEMA_VERSION_METADATA_KEY) != str(
        B3_SCHEMA_VERSION
    ).encode('ascii'):
        raise ExtractionError(
            'B3 Parquet', 'Schema version metadata is invalid'
        )
    if metadata.get(B3_SCHEMA_FINGERPRINT_METADATA_KEY) != (
        expected_fingerprint.encode('ascii')
    ):
        raise ExtractionError(
            'B3 Parquet', 'Logical schema fingerprint metadata is invalid'
        )
    raw_manifest = metadata.get(B3_AUDIT_METADATA_KEY)
    if raw_manifest is None:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is missing'
        )
    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is invalid'
        ) from error
    if not isinstance(manifest, dict):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest is invalid'
        )
    if (
        manifest.get('schema_version') != B3_SCHEMA_VERSION
        or manifest.get('logical_schema_fingerprint') != expected_fingerprint
    ):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer manifest schema is incompatible'
        )
    expected_digests = [
        {
            'year': source.year,
            'source': source.path.name,
            'rows_sha256': source.expected_rows_sha256,
        }
        for source in sources
    ]
    if manifest.get('ordered_content_digests') != expected_digests:
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer ordered digests are incompatible'
        )
    if metadata != (expected_schema.metadata or {}):
        raise ExtractionError(
            'B3 Parquet', 'Integrity footer metadata differs from preflight'
        )
