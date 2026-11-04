"""Serialize COTAHIST observations for public and persisted reports."""

from __future__ import annotations

import base64

from .models import ValidatedCotahistSource


def build_source_evidence(
    source: ValidatedCotahistSource,
) -> dict[str, object]:
    """Preserve source identities, controls, counts, dates, and warnings."""
    return {
        'source': source.path.name,
        'year': source.year,
        'member': source.member,
        'outer_sha256': source.outer_sha256,
        'content_sha256': source.content_sha256,
        'uncompressed_bytes': source.uncompressed_bytes,
        'raw_quotes': source.raw_quotes,
        'selected_quotes': source.selected_quotes,
        'intentional_exclusions': source.intentional_exclusions,
        'market_counts': dict(source.market_counts),
        'unknown_market_counts': dict(source.unknown_market_counts),
        'header_records': 1,
        'trailer_records': 1,
        'header_base64': base64.b64encode(source.header_bytes).decode('ascii'),
        'trailer_base64': base64.b64encode(source.trailer_bytes).decode(
            'ascii'
        ),
        'generation_date': source.generation_date.isoformat(),
        'declared_records': source.declared_records,
        'trailer_convention': source.trailer_convention,
        'blank_lines': source.blank_lines,
        'first_trading_date': source.first_trading_date.isoformat(),
        'last_trading_date': source.last_trading_date.isoformat(),
        'expected_rows_sha256': source.expected_rows_sha256,
        'warnings': [
            {
                'code': warning.code,
                'count': warning.count,
                'explanation': warning.explanation,
            }
            for warning in source.warnings
        ],
    }
