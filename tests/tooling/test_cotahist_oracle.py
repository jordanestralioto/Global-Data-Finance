"""Independent COTAHIST raw-to-Parquet acceptance checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    cotahist_parser,
)
from scripts.cotahist_oracle import OracleMismatch, reconcile_sources
from scripts.cotahist_oracle.manifest_validation import read_manifest
from scripts.cotahist_oracle.row_decoder import decode_field
from scripts.cotahist_oracle.schema import (
    FIELD_DEFINITIONS,
    FieldDefinition,
    independent_schema,
    validate_schema,
)
from scripts.cotahist_oracle.source_reader import (
    SourceFacts,
    inspect_source,
    validate_header,
    validate_trailer,
)
from tests.support.builders import (
    build_cotahist_header,
    build_cotahist_record,
    build_cotahist_trailer,
    write_cotahist_txt,
    write_cotahist_zip,
)


def _extract_all_markets(
    source_directory: Path, output_directory: Path
) -> dict:
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(source_directory),
        assets_list=['todos'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(output_directory),
        output_filename='oracle-check',
        verbose=False,
    )
    return dict(result)


@pytest.mark.integration
def test_oracle_reconciles_every_source_field_and_public_report(
    tmp_path: Path,
) -> None:
    """A complete public extraction matches an independent raw decoder."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    output_directory = tmp_path / 'output'
    output_directory.mkdir()

    result = _extract_all_markets(tmp_path, output_directory)
    reconciliation = reconcile_sources(
        [source], Path(result['output_file']), public_result=result
    )

    assert reconciliation['rawQuotes'] == 1
    assert reconciliation['selectedQuotes'] == 1
    assert reconciliation['verifiedRows'] == 1
    assert reconciliation['previousTwentyFieldsEqual'] is True


@pytest.mark.integration
def test_oracle_detects_a_production_parser_offset_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The independent offsets expose a self-consistent parser mistake."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    layout = list(cotahist_parser.parser.B3_QUOTATION_LAYOUT)
    price_index = next(
        index
        for index, field in enumerate(layout)
        if field.name == 'preco_abertura'
    )
    price_start = layout[price_index].start
    price_stop = layout[price_index].stop
    assert price_start is not None and price_stop is not None
    layout[price_index] = replace(
        layout[price_index],
        start=price_start + 1,
        stop=price_stop + 1,
    )
    monkeypatch.setattr(
        cotahist_parser.parser, 'B3_QUOTATION_LAYOUT', tuple(layout)
    )

    result = _extract_all_markets(tmp_path, output_directory)

    assert result['success'] is True
    with pytest.raises(OracleMismatch, match='field preco_abertura differs'):
        reconcile_sources(
            [source], Path(result['output_file']), public_result=result
        )


@pytest.mark.integration
def test_oracle_detects_a_self_consistent_production_scale_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independent decimals expose a wrong scale despite matching digests."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    output = tmp_path / 'output'
    normalize = cotahist_parser.field_conversion.normalize_decimal

    def wrong_scale(
        raw_value: str,
        scale: int,
        context=None,
        *,
        field_name: str = 'decimal',
    ) -> str:
        if field_name == 'preco_abertura':
            value = normalize(raw_value, 1, context, field_name=field_name)
            return format(Decimal(value), '.2f')
        return normalize(raw_value, scale, context, field_name=field_name)

    monkeypatch.setattr(
        cotahist_parser.field_conversion, 'normalize_decimal', wrong_scale
    )

    result = _extract_all_markets(tmp_path, output)

    assert result['success'] is True
    assert result['integrity']['status'] == 'passed'
    with pytest.raises(OracleMismatch, match='field preco_abertura differs'):
        reconcile_sources(
            [source], Path(result['output_file']), public_result=result
        )


@pytest.mark.integration
def test_oracle_covers_txt_blank_lines_block_lot_and_unknown_markets(
    tmp_path: Path,
) -> None:
    """The independent reader retains controls, lines, and every market."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(year=2024, ticker='BBT1', market='021'),
            build_cotahist_record(year=2024, ticker='MYSTERY', market='999'),
        ],
    )
    contents = source.read_bytes().replace(b'\n', b'\r\n')
    source.write_bytes(contents.replace(b'\r\n01', b'\r\n\r\n01', 1))
    output_directory = tmp_path / 'output'
    output_directory.mkdir()

    result = _extract_all_markets(tmp_path, output_directory)
    reconciliation = reconcile_sources(
        [source],
        Path(result['output_file']),
        public_result=result,
        expected_checksums={
            source.name: hashlib.sha256(source.read_bytes()).hexdigest()
        },
        batch_size=1,
    )

    assert reconciliation['marketCounts'] == {'021': 1, '999': 1}
    assert reconciliation['unknownMarketCounts'] == {'999': 1}
    assert reconciliation['blockLotRowsByYear'] == {2024: 1}
    assert reconciliation['blankLines'] == {source.name: 1}
    assert reconciliation['sourceChecksums'][0]['source'] == source.name


@pytest.mark.unit
def test_oracle_rejects_empty_ranges_and_bad_source_identity(
    tmp_path: Path,
) -> None:
    """The independent executor rejects invalid invocation and file names."""
    with pytest.raises(ValueError, match='batch_size'):
        reconcile_sources(
            [tmp_path / 'COTAHIST_A2024.TXT'], tmp_path, batch_size=0
        )
    with pytest.raises(ValueError, match='at least one'):
        reconcile_sources([], tmp_path)
    with pytest.raises(OracleMismatch, match='invalid COTAHIST input path'):
        inspect_source(tmp_path / 'other.txt')


@pytest.mark.unit
def test_oracle_control_and_numeric_decoders_are_exact(tmp_path: Path) -> None:
    """Control, decimal, date, and text rules are independently explicit."""
    source = SourceFacts(
        path=tmp_path / 'COTAHIST_A2024.TXT',
        year=2024,
        member='',
        outer_sha256='',
        content_sha256='',
        uncompressed_bytes=0,
    )
    header = build_cotahist_header(2024).encode()
    trailer = build_cotahist_trailer(2024, 1).encode()
    assert validate_header(header, source, 1).year == 2024
    source.header = header
    source.quote_count = 1
    validate_trailer(trailer, source, 3)
    assert source.declared_count == 3

    by_name = {field.name: field for field in FIELD_DEFINITIONS}
    assert decode_field(
        by_name['preco_abertura'], b'0000000012345', 2024, 'x', 2
    ) == Decimal('123.45')
    assert decode_field(
        by_name['preco_exercicio_pontos'],
        b'0000012345678',
        2024,
        'x',
        2,
    ) == Decimal('12.345678')
    assert (
        decode_field(by_name['data_vencimento'], b'00000000', 2024, 'x', 2)
        is None
    )
    assert (
        decode_field(by_name['data_vencimento'], b'        ', 2024, 'x', 2)
        is None
    )
    assert (
        decode_field(by_name['moeda_referencia'], b' BRL', 2024, 'x', 2)
        == 'BRL'
    )


@pytest.mark.parametrize(
    ('decoder', 'value', 'message'),
    [
        ('market', b'0A0', 'three ASCII digits'),
        ('required_text', b'            ', 'is empty'),
        ('integer', b'00 01', 'ASCII digits'),
        ('integer', b' 0001', 'ASCII digits'),
        ('decimal', b'000000000001 ', 'ASCII digits'),
        ('numeric_code', b'A', 'ASCII digits'),
        ('numeric_code', b' ', 'ASCII digits'),
        ('decimal', b'00000000000A0', 'ASCII digits'),
        ('date', b'20240231', 'not a valid date'),
    ],
)
@pytest.mark.unit
def test_oracle_rejects_invalid_quote_fields(
    decoder: str, value: bytes, message: str
) -> None:
    """The oracle refuses invalid market, text, number, and date fields."""
    field = FieldDefinition(
        name='fixture',
        arrow_type='large_string',
        conversion=decoder,
        scale=2 if decoder == 'decimal' else 0,
    )

    with pytest.raises(OracleMismatch, match=message):
        decode_field(field, value, 2024, 'fixture', 1)


@pytest.mark.unit
def test_oracle_checks_schema_and_manifest_metadata() -> None:
    """A pandas schema or malformed footer cannot satisfy the oracle."""
    schema = independent_schema().with_metadata({b'pandas': b'{}'})
    with pytest.raises(OracleMismatch, match='pandas metadata'):
        validate_schema(schema)
    with pytest.raises(OracleMismatch, match='invalid version'):
        read_manifest(
            {
                b'globaldatafinance.b3.integrity_manifest': (
                    b'{"schema_version": 1}'
                )
            }
        )
    with pytest.raises(OracleMismatch, match='malformed'):
        read_manifest({b'globaldatafinance.b3.integrity_manifest': b'{bad'})


@pytest.mark.parametrize(
    ('path', 'value'),
    [
        (('logical_schema_fingerprint',), '0' * 64),
        (('layout_reference',), 'incorrect layout'),
        (('selection', 'asset_classes'), ['ações']),
        (('selection', 'market_codes'), ['999']),
        (('sources', 0, 'market_counts'), {}),
        (('sources', 0, 'unknown_market_counts'), {}),
        (('sources', 0, 'warnings'), []),
        (('sources', 0, 'expected_rows_sha256'), '0' * 64),
        (('ordered_content_digests', 0, 'rows_sha256'), '0' * 64),
        (('verification_policy', 'compare'), []),
    ],
)
@pytest.mark.integration
def test_oracle_rejects_tampered_footer_with_unchanged_rows(
    tmp_path: Path, path: tuple[str | int, ...], value: object
) -> None:
    """Exact row equality cannot conceal false persisted audit evidence."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, market='999')],
    )
    result = _extract_all_markets(tmp_path, tmp_path / 'output')
    output = Path(result['output_file'])
    table = pq.read_table(output)
    metadata = dict(table.schema.metadata or {})
    key = b'globaldatafinance.b3.integrity_manifest'
    manifest = json.loads(metadata[key])
    target = manifest
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    metadata[key] = json.dumps(manifest).encode()
    pq.write_table(table.replace_schema_metadata(metadata), output)

    with pytest.raises(OracleMismatch, match='footer'):
        reconcile_sources([source], output)


@pytest.mark.parametrize(
    ('key', 'value'),
    [
        ('unknown_market_counts', {}),
        ('asset_classes', ['ações']),
        ('requested_years', [2023]),
        ('source_first_trading_date', '2024-12-31'),
        ('output_last_trading_date', '2024-01-01'),
        ('verification_method', 'not completed'),
    ],
)
@pytest.mark.integration
def test_oracle_rejects_false_public_observations(
    tmp_path: Path, key: str, value: object
) -> None:
    """Public audit observations must agree with independently decoded data."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, market='999')],
    )
    result = _extract_all_markets(tmp_path, tmp_path / 'output')
    result['integrity'][key] = value

    with pytest.raises(OracleMismatch, match='public integrity'):
        reconcile_sources(
            [source], Path(result['output_file']), public_result=result
        )


@pytest.mark.integration
def test_oracle_volume_sum_is_independent_of_decimal_context(
    tmp_path: Path,
) -> None:
    """Maximum source-width sums remain exact under low caller precision."""
    record = build_cotahist_record(year=2024, market='021')
    record = record[:170] + '999999999999999999' + record[188:]
    source = write_cotahist_zip(tmp_path, year=2024, records=[record, record])
    result = _extract_all_markets(tmp_path, tmp_path / 'output')

    with localcontext() as context:
        context.prec = 6
        reconciliation = reconcile_sources(
            [source], Path(result['output_file']), public_result=result
        )

    assert reconciliation['blockLotVolumeTotal'] == '19999999999999999.98'
