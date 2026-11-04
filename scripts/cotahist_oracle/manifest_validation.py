"""Validate independent schema and extraction integrity manifests."""

from __future__ import annotations

import base64
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.cotahist_oracle.errors import OracleMismatch
from scripts.cotahist_oracle.schema import (
    independent_schema,
    schema_fingerprint,
)
from scripts.cotahist_oracle.source_reader import SourceFacts, sha256_file

SCHEMA_VERSION_KEY = b'globaldatafinance.b3.schema_version'

SCHEMA_FINGERPRINT_KEY = b'globaldatafinance.b3.schema_fingerprint'

MANIFEST_KEY = b'globaldatafinance.b3.integrity_manifest'

LAYOUT_REFERENCE = (
    'https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/'
    'SeriesHistoricas_Layout.pdf'
)

VERIFICATION_CHECKS = [
    'schema_and_metadata',
    'row_counts',
    'required_column_null_counts',
    'source_boundaries_and_coordinates',
    'ordered_logical_rows',
    'original_quotation_bytes',
    'per_source_ordered_content_digests',
    'source_checksums_before_commit',
]


def read_manifest(metadata: dict[bytes, bytes]) -> dict[str, Any]:
    """Decode the Parquet integrity manifest."""
    payload = metadata.get(MANIFEST_KEY)
    if payload is None:
        raise OracleMismatch('Parquet audit manifest is missing')
    try:
        manifest = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OracleMismatch('Parquet audit manifest is malformed') from error
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 2:
        raise OracleMismatch('Parquet audit manifest has an invalid version')
    return manifest


def validate_manifest_identity(
    manifest: dict[str, Any], source_facts: Sequence[SourceFacts]
) -> None:
    """Check that a manifest describes the selected source files."""
    if (
        manifest.get('logical_schema_fingerprint')
        != schema_fingerprint(independent_schema())
        or manifest.get('layout_reference') != LAYOUT_REFERENCE
    ):
        raise OracleMismatch('footer schema fingerprint or layout is invalid')
    expected = [
        {
            'year': source.year,
            'source': source.path.name,
        }
        for source in source_facts
    ]
    actual = manifest.get('ordered_content_digests')
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise OracleMismatch('footer source digest list is incomplete')
    for item, source in zip(actual, source_facts, strict=True):
        if (
            not isinstance(item, dict)
            or item.get('year') != source.year
            or item.get('source') != source.path.name
            or not is_sha256(item.get('rows_sha256'))
        ):
            raise OracleMismatch('footer source digest identity is invalid')
    manifest_sources = manifest.get('sources')
    if not isinstance(manifest_sources, list) or len(manifest_sources) != len(
        source_facts
    ):
        raise OracleMismatch('footer source report list is incomplete')
    for item, source in zip(manifest_sources, source_facts, strict=True):
        if (
            not isinstance(item, dict)
            or item.get('source') != source.path.name
            or item.get('year') != source.year
            or item.get('member') != source.member
            or item.get('outer_sha256') != source.outer_sha256
            or item.get('content_sha256') != source.content_sha256
            or item.get('uncompressed_bytes') != source.uncompressed_bytes
        ):
            raise OracleMismatch(
                'footer source identity differs from raw input'
            )


def validate_manifest_counts(
    manifest: dict[str, Any],
    source_facts: Sequence[SourceFacts],
    total_rows: int,
) -> None:
    """Compare manifest counts with independently scanned source totals."""
    counts = manifest.get('expected_counts')
    if not isinstance(counts, dict):
        raise OracleMismatch('footer expected counts are missing')
    expected = {
        'raw_quotes': total_rows,
        'selected_quotes': total_rows,
        'intentional_exclusions': 0,
        'written_rows': total_rows,
    }
    if any(counts.get(name) != value for name, value in expected.items()):
        raise OracleMismatch('footer expected counts differ from raw contents')
    requested = manifest.get('requested_years')
    expected_years = [source.year for source in source_facts]
    if requested != expected_years:
        raise OracleMismatch('footer requested year range differs from inputs')
    source_reports = manifest.get('sources')
    if not isinstance(source_reports, list) or len(source_reports) != len(
        source_facts
    ):
        raise OracleMismatch('footer source reports are invalid')
    for item, source in zip(source_reports, source_facts, strict=True):
        _validate_source_observations(item, source, 'footer')
    for digest, source in zip(
        manifest['ordered_content_digests'], source_facts, strict=True
    ):
        if digest.get('rows_sha256') != source.rows_digest.hexdigest():
            raise OracleMismatch(
                'footer ordered source digest differs from raw rows'
            )
    selection = manifest.get('selection')
    if (
        not isinstance(selection, dict)
        or selection.get('complete_market_selection') is not True
        or selection.get('asset_classes') != ['todos']
        or selection.get('market_codes') != []
    ):
        raise OracleMismatch(
            'footer does not record complete market selection'
        )
    policy = manifest.get('verification_policy')
    if (
        not isinstance(policy, dict)
        or policy.get('method')
        != 'bounded full Parquet readback before publication'
        or policy.get('compare') != VERIFICATION_CHECKS
    ):
        raise OracleMismatch('footer verification policy is invalid')


def _validate_source_observations(
    item: object, source: SourceFacts, context: str
) -> None:
    """Check source observations shared by footer and public reports."""
    expected_source_values = {
        'raw_quotes': source.quote_count,
        'selected_quotes': source.quote_count,
        'intentional_exclusions': 0,
        'market_counts': source.market_counts,
        'unknown_market_counts': source.unknown_market_counts,
        'expected_rows_sha256': source.rows_digest.hexdigest(),
        'header_records': 1,
        'trailer_records': 1,
        'declared_records': source.declared_count,
        'trailer_convention': source.trailer_convention,
        'blank_lines': source.blank_lines,
        'generation_date': (
            source.generation_date.isoformat()
            if source.generation_date is not None
            else None
        ),
        'first_trading_date': (
            source.first_date.isoformat()
            if source.first_date is not None
            else None
        ),
        'last_trading_date': (
            source.last_date.isoformat()
            if source.last_date is not None
            else None
        ),
        'header_base64': base64.b64encode(source.header or b'').decode(
            'ascii'
        ),
        'trailer_base64': base64.b64encode(source.trailer or b'').decode(
            'ascii'
        ),
    }
    if not isinstance(item, dict) or any(
        item.get(name) != value
        for name, value in expected_source_values.items()
    ):
        raise OracleMismatch(
            f'{context} source report differs from raw contents: '
            f'{source.path.name}'
        )
    if item.get('warnings') != _expected_source_warnings(source):
        raise OracleMismatch(
            f'{context} source warnings differ from raw contents'
        )


def _expected_source_warnings(source: SourceFacts) -> list[dict[str, Any]]:
    """Derive stable warning records from independent source observations."""
    warnings = []
    if source.blank_lines:
        warnings.append(
            {
                'code': 'BLANK_PHYSICAL_LINES',
                'count': source.blank_lines,
                'explanation': (
                    'Empty physical lines were counted and ignored.'
                ),
            }
        )
    if source.trailer_convention == 'quotes_only':
        warnings.append(
            {
                'code': 'TRAILER_QUOTES_ONLY',
                'count': 1,
                'explanation': (
                    'Trailer count includes quotations but omits the '
                    'header and trailer controls.'
                ),
            }
        )
    warnings.extend(
        {
            'code': 'UNKNOWN_TPMERC',
            'count': count,
            'explanation': f'Unknown numeric TPMERC {code} was preserved or '
            'intentionally excluded by the requested selection.',
        }
        for code, count in sorted(source.unknown_market_counts.items())
    )
    return warnings


def validate_public_result(
    result: dict[str, Any],
    source_facts: Sequence[SourceFacts],
    total_rows: int,
) -> None:
    """Compare public extraction results with independent source facts."""
    integrity = result.get('integrity')
    if not isinstance(integrity, dict):
        raise OracleMismatch('public result has no integrity report')
    _validate_public_observations(integrity, source_facts)
    required = (
        result.get('success') is True,
        result.get('schema_version') == 2,
        result.get('total_files') == len(source_facts),
        result.get('success_count') == len(source_facts),
        result.get('error_count') == 0,
        result.get('total_records') == total_rows,
        result.get('errors') == {},
        integrity.get('status') == 'passed',
        integrity.get('selection_complete') is True,
        integrity.get('source_complete') is True,
        integrity.get('missing_years') == [],
        integrity.get('raw_quotes') == total_rows,
        integrity.get('selected_quotes') == total_rows,
        integrity.get('written_rows') == total_rows,
        integrity.get('verified_rows') == total_rows,
        integrity.get('intentional_exclusions') == 0,
        integrity.get('output_sha256')
        == sha256_file(Path(result['output_file'])),
        integrity.get('selected_years')
        == [source.year for source in source_facts],
        integrity.get('complete_market_selection') is True,
        integrity.get('market_codes') == [],
    )
    if not all(required):
        raise OracleMismatch(
            'public result counters disagree with raw/output facts'
        )
    source_reports = integrity.get('sources')
    if not isinstance(source_reports, list) or len(source_reports) != len(
        source_facts
    ):
        raise OracleMismatch('public source integrity reports are incomplete')
    for item, source in zip(source_reports, source_facts, strict=True):
        _validate_source_observations(item, source, 'public')
        if (
            not isinstance(item, dict)
            or item.get('source') != source.path.name
            or item.get('year') != source.year
            or item.get('outer_sha256') != source.outer_sha256
            or item.get('content_sha256') != source.content_sha256
            or item.get('raw_quotes') != source.quote_count
            or item.get('selected_quotes') != source.quote_count
            or item.get('written_rows') != source.quote_count
            or item.get('verified_rows') != source.quote_count
            or item.get('verified_rows_sha256')
            != source.rows_digest.hexdigest()
        ):
            raise OracleMismatch(
                f'public source report differs from raw contents: '
                f'{source.path.name}'
            )


def _validate_public_observations(
    integrity: dict[str, Any], source_facts: Sequence[SourceFacts]
) -> None:
    """Reconcile public selection, date bounds and unknown-market totals."""
    dates = [
        value
        for source in source_facts
        for value in (source.first_date, source.last_date)
        if value is not None
    ]
    unknown: Counter[str] = Counter()
    for source in source_facts:
        unknown.update(source.unknown_market_counts)
    expected = {
        'schema_version': 2,
        'requested_years': [source.year for source in source_facts],
        'asset_classes': ['todos'],
        'excluded_records': 0,
        'unknown_market_counts': dict(unknown),
        'source_first_trading_date': min(dates).isoformat(),
        'source_last_trading_date': max(dates).isoformat(),
        'output_first_trading_date': min(dates).isoformat(),
        'output_last_trading_date': max(dates).isoformat(),
        'verification_method': (
            'bounded full Parquet readback against preflight source digests'
        ),
    }
    if any(integrity.get(name) != value for name, value in expected.items()):
        raise OracleMismatch(
            'public integrity observations differ from raw contents'
        )


def validate_expected_checksums(
    source_facts: Sequence[SourceFacts], expected_checksums: dict[str, str]
) -> None:
    """Require source checksums to match the supplied frozen manifest."""
    actual = {fact.path.name: fact.outer_sha256 for fact in source_facts}
    if actual != expected_checksums:
        changed = sorted(
            name
            for name in set(actual) | set(expected_checksums)
            if actual.get(name) != expected_checksums.get(name)
        )
        raise OracleMismatch(
            f'frozen COTAHIST source checksum manifest differs: {changed}'
        )


def is_sha256(value: object) -> bool:
    """Return whether a value is a lowercase SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in '0123456789abcdef' for character in value)
    )
