"""Full readback rejects corrupted persisted B3 contracts and occurrences."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.integrity import (
    B3RecordContext,
)
from globaldatafinance.brazil.b3_data.historical_quotes.models import (
    ValidatedCotahistSource,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    audit_metadata as b3_audit,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    schema as b3_schema,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    verification as b3_verification,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


@pytest.fixture
def verified_input(
    tmp_path: Path,
) -> tuple[pa.Table, ValidatedCotahistSource]:
    """Derive row expectations from the source before writing the candidate."""
    records = [
        build_cotahist_record(year=2024, ticker=ticker)
        for ticker in ('PETR4', 'VALE3')
    ]
    write_cotahist_txt(tmp_path, year=2024, records=records)
    source = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes=set(),
        all_markets=True,
    ).sources[0]
    metadata = b3_audit.build_b3_audit_metadata(
        (source,),
        schema_fingerprint=b3_schema.schema_fingerprint(
            b3_schema.build_b3_schema()
        ),
        requested_years=(2024,),
        asset_classes=('todos',),
        target_tpmerc_codes=set(),
        all_markets=True,
    )
    parser = CotahistParserB3()
    rows = [
        parser.parse_line(
            record,
            set(),
            B3RecordContext(source.path.name, '', index + 2, index + 1),
            all_markets=True,
            source_year=source.year,
            source_sha256=source.content_sha256,
        )
        for index, record in enumerate(records)
    ]
    return pa.Table.from_pylist(
        rows, schema=b3_schema.build_b3_schema(metadata)
    ), source


def test_readback_proves_source_rows_and_dates(
    tmp_path: Path,
    verified_input: tuple[pa.Table, ValidatedCotahistSource],
) -> None:
    """An unmodified candidate matches all preflight-derived evidence."""
    table, source = verified_input
    output = tmp_path / 'verified.parquet'
    pq.write_table(table, output)

    result = b3_verification.verify_b3_parquet(
        output, expected_schema=table.schema, sources=(source,)
    )

    assert result.row_count == 2
    assert result.source_row_counts == (2,)
    assert result.source_digests == (source.expected_rows_sha256,)
    assert (
        result.first_trading_date
        == result.last_trading_date
        == date(2024, 1, 15)
    )


@pytest.mark.parametrize(
    'manifest_field',
    [
        'layout_reference',
        'requested_years',
        'selection',
        'expected_counts',
        'sources',
        'verification_policy',
    ],
)
def test_readback_rejects_changed_footer_evidence(
    tmp_path: Path,
    verified_input: tuple[pa.Table, ValidatedCotahistSource],
    manifest_field: str,
) -> None:
    """Unchanged logical rows cannot conceal altered dynamic audit facts."""
    table, source = verified_input
    metadata = dict(table.schema.metadata or {})
    manifest = json.loads(metadata[b3_audit.B3_AUDIT_METADATA_KEY])
    manifest[manifest_field] = None
    metadata[b3_audit.B3_AUDIT_METADATA_KEY] = json.dumps(manifest).encode()
    output = tmp_path / 'tampered.parquet'
    pq.write_table(table.replace_schema_metadata(metadata), output)

    with pytest.raises(ExtractionError, match='metadata differs'):
        b3_verification.verify_b3_parquet(
            output, expected_schema=table.schema, sources=(source,)
        )


@pytest.mark.parametrize('manifest', [b'[]', b'null', b'"manifest"', b'{'])
def test_readback_rejects_malformed_manifest(
    tmp_path: Path,
    verified_input: tuple[pa.Table, ValidatedCotahistSource],
    manifest: bytes,
) -> None:
    """Malformed JSON and non-object manifests produce contextual failure."""
    table, source = verified_input
    metadata = dict(table.schema.metadata or {})
    metadata[b3_audit.B3_AUDIT_METADATA_KEY] = manifest
    output = tmp_path / 'malformed.parquet'
    pq.write_table(table.replace_schema_metadata(metadata), output)

    with pytest.raises(ExtractionError, match='manifest is invalid'):
        b3_verification.verify_b3_parquet(
            output, expected_schema=table.schema, sources=(source,)
        )


@pytest.mark.parametrize('mutation', ['drop', 'repeat', 'reorder'])
def test_readback_rejects_changed_source_occurrences(
    tmp_path: Path,
    verified_input: tuple[pa.Table, ValidatedCotahistSource],
    mutation: str,
) -> None:
    """Missing, duplicated, and reordered source occurrences fail readback."""
    table, source = verified_input
    indices = {'drop': [0], 'repeat': [0, 0], 'reorder': [1, 0]}[mutation]
    output = tmp_path / 'occurrences.parquet'
    pq.write_table(table.take(indices), output)

    with pytest.raises(ExtractionError, match=r'row count|digest mismatch'):
        b3_verification.verify_b3_parquet(
            output, expected_schema=table.schema, sources=(source,)
        )


@pytest.mark.parametrize(
    ('column', 'value'),
    [
        ('preco_abertura', Decimal('0.01')),
        ('registro_original', b'X' * 245),
        ('linha_origem', 99),
        ('id_fonte', '0' * 64),
        ('arquivo_origem', 'COTAHIST_A2023.TXT'),
        ('membro_origem', 'wrong.txt'),
        ('ano_origem', 2023),
    ],
)
def test_readback_rejects_changed_values_and_provenance(
    tmp_path: Path,
    verified_input: tuple[pa.Table, ValidatedCotahistSource],
    column: str,
    value: object,
) -> None:
    """Exact financial, binary, and coordinate changes invalidate output."""
    table, source = verified_input
    rows = table.to_pylist()
    rows[0][column] = value
    output = tmp_path / 'values.parquet'
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), output)

    with pytest.raises(ExtractionError, match=r'digest mismatch|boundary'):
        b3_verification.verify_b3_parquet(
            output, expected_schema=table.schema, sources=(source,)
        )
