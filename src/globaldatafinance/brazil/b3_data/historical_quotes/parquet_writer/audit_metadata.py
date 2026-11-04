"""Versioned self-contained B3 Parquet audit metadata."""

from __future__ import annotations

import json
from collections.abc import Sequence

from ..models import ValidatedCotahistSource
from ..source_evidence import build_source_evidence
from .schema import B3_SCHEMA_VERSION

B3_LAYOUT_REFERENCE = (
    'https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/'
    'SeriesHistoricas_Layout.pdf'
)
B3_AUDIT_METADATA_KEY = b'globaldatafinance.b3.integrity_manifest'
B3_SCHEMA_VERSION_METADATA_KEY = b'globaldatafinance.b3.schema_version'
B3_SCHEMA_FINGERPRINT_METADATA_KEY = b'globaldatafinance.b3.schema_fingerprint'


def build_b3_audit_metadata(
    sources: Sequence[ValidatedCotahistSource],
    *,
    schema_fingerprint: str,
    requested_years: Sequence[int],
    asset_classes: Sequence[str],
    target_tpmerc_codes: set[str],
    all_markets: bool,
) -> dict[bytes, bytes]:
    """Build deterministic metadata before any source artifact is opened."""
    source_entries = [build_source_evidence(source) for source in sources]
    manifest = {
        'schema_version': B3_SCHEMA_VERSION,
        'logical_schema_fingerprint': schema_fingerprint,
        'layout_reference': B3_LAYOUT_REFERENCE,
        'requested_years': list(requested_years),
        'selection': {
            'complete_market_selection': all_markets,
            'asset_classes': sorted(set(asset_classes)),
            'market_codes': sorted(target_tpmerc_codes),
        },
        'expected_counts': {
            'raw_quotes': sum(source.raw_quotes for source in sources),
            'selected_quotes': sum(
                source.selected_quotes for source in sources
            ),
            'intentional_exclusions': sum(
                source.intentional_exclusions for source in sources
            ),
            'written_rows': sum(source.selected_quotes for source in sources),
        },
        'ordered_content_digests': [
            {
                'year': source.year,
                'source': source.path.name,
                'rows_sha256': source.expected_rows_sha256,
            }
            for source in sources
        ],
        'sources': source_entries,
        'verification_policy': {
            'method': 'bounded full Parquet readback before publication',
            'compare': [
                'schema_and_metadata',
                'row_counts',
                'required_column_null_counts',
                'source_boundaries_and_coordinates',
                'ordered_logical_rows',
                'original_quotation_bytes',
                'per_source_ordered_content_digests',
                'source_checksums_before_commit',
            ],
        },
    }
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return {
        B3_SCHEMA_VERSION_METADATA_KEY: str(B3_SCHEMA_VERSION).encode('ascii'),
        B3_SCHEMA_FINGERPRINT_METADATA_KEY: schema_fingerprint.encode('ascii'),
        B3_AUDIT_METADATA_KEY: manifest_bytes,
    }
