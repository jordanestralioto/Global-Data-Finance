"""Reject invalid annual documents before creating publication artifacts."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from tests.support.builders import (
    build_cotahist_header,
    build_cotahist_record,
    build_cotahist_trailer,
    write_zip,
)

pytestmark = pytest.mark.integration


def _replace(record: str, start: int, stop: int, value: str) -> str:
    assert len(value) == stop - start
    return record[:start] + value + record[stop:]


def _invalid_documents() -> list[tuple[str, list[str], str]]:
    header = build_cotahist_header(2024)
    quote = build_cotahist_record(year=2024, market='070')
    trailer = build_cotahist_trailer(2024, 1)
    cases = [
        ('missing-header', [quote, trailer], 'record_type'),
        ('missing-trailer', [header, quote], 'trailer'),
        ('repeated-header', [header, header, quote, trailer], 'record_type'),
        ('repeated-trailer', [header, quote, trailer, trailer], 'record_type'),
        (
            'quote-after-trailer',
            [header, quote, trailer, quote],
            'record_type',
        ),
        ('no-quotes', [header, trailer], 'record_type'),
        ('unknown-type', [header, '02' + quote[2:], trailer], 'record_type'),
        ('short-control', [header[:-1], quote, trailer], 'record_length'),
        ('long-quote', [header, quote + ' ', trailer], 'record_length'),
    ]
    for name, index, start, stop, value, field in [
        ('header-name', 0, 2, 15, 'COTAHIST.2023', 'control_filename'),
        ('header-origin', 0, 15, 23, 'INVALID ', 'control_origin'),
        ('header-date', 0, 23, 31, '20240230', 'generation_date'),
        ('header-reserve', 0, 31, 32, 'X', 'header_reserved'),
        ('trailer-name', 2, 2, 15, 'COTAHIST.2023', 'control_filename'),
        ('trailer-origin', 2, 15, 23, 'INVALID ', 'control_origin'),
        ('trailer-date', 2, 23, 31, '20240101', 'trailer_identity'),
        ('trailer-reserve', 2, 42, 43, 'X', 'trailer_reserved'),
        ('trailer-count-text', 2, 31, 42, '0000000000X', 'declared_records'),
        ('trailer-count-wrong', 2, 31, 42, '00000000002', 'record total'),
    ]:
        lines = [header, quote, trailer]
        lines[index] = _replace(lines[index], start, stop, value)
        cases.append((name, lines, field))
    for name, start, stop in [
        ('preco_abertura', 56, 69),
        ('preco_maximo', 69, 82),
        ('preco_minimo', 82, 95),
        ('preco_medio', 95, 108),
        ('preco_fechamento', 108, 121),
        ('melhor_oferta_compra', 121, 134),
        ('melhor_oferta_venda', 134, 147),
        ('numero_negocios', 147, 152),
        ('quantidade_total', 152, 170),
        ('volume_total', 170, 188),
        ('preco_exercicio', 188, 201),
        ('indicador_correcao', 201, 202),
        ('fator_cotacao', 210, 217),
        ('preco_exercicio_pontos', 217, 230),
        ('numero_distribuicao', 242, 245),
    ]:
        for side in ('leading', 'trailing'):
            original = quote[start:stop]
            value = (
                ' ' + original[1:]
                if side == 'leading'
                else original[:-1] + ' '
            )
            cases.append(
                (
                    f'{name}-{side}-space',
                    [header, _replace(quote, start, stop, value), trailer],
                    name,
                )
            )
    cases.append(
        (
            'non-numeric-indicator',
            [header, _replace(quote, 201, 202, 'A'), trailer],
            'indicador_correcao',
        )
    )
    return cases


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
@pytest.mark.parametrize(
    ('case', 'lines', 'diagnostic'),
    _invalid_documents(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_invalid_document_fails_before_destination_creation(
    tmp_path: Path,
    extension: str,
    case: str,
    lines: list[str],
    diagnostic: str,
) -> None:
    """Excluded markets still undergo every field and document check."""
    sources = tmp_path / case
    sources.mkdir()
    source = sources / f'COTAHIST_A2024.{extension}'
    payload = ('\n'.join(lines) + '\n').encode('latin-1')
    if extension == 'ZIP':
        write_zip(source, {'COTAHIST_A2024.TXT': payload})
    else:
        source.write_bytes(payload)
    destination = tmp_path / 'uncreated-output'

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(sources),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(destination),
        verbose=False,
    )

    assert result['success'] is False
    assert result['success_count'] == result['total_records'] == 0
    assert result['output_file'] == ''
    assert result['error_count'] == 1
    assert diagnostic in result['errors'][source.name]
    assert result['integrity']['written_rows'] == 0
    assert result['integrity']['verified_rows'] == 0
    assert not destination.exists()


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
@pytest.mark.parametrize('mode', ['fast', 'slow'])
@pytest.mark.parametrize('market', ['010', '017'])
def test_utf8_source_requires_an_explicit_latin1_copy(
    tmp_path: Path, extension: str, mode: str, market: str
) -> None:
    """Encoding recovery preserves text, bytes, and the original source."""
    quote = _replace(
        build_cotahist_record(market=market), 27, 39, 'FROTA OCEÂNI'
    )
    text = (
        '\r\n'.join(
            [
                build_cotahist_header(2024),
                quote,
                build_cotahist_record(),
                build_cotahist_trailer(2024, 2),
            ]
        )
        + '\r\n'
    )
    original_payload = text.encode('utf-8')
    sources = tmp_path / 'original'
    sources.mkdir()
    original = sources / f'COTAHIST_A2024.{extension}'
    if extension == 'ZIP':
        write_zip(original, {'COTAHIST_A2024.TXT': original_payload})
    else:
        original.write_bytes(original_payload)
    original_bytes = original.read_bytes()
    destination = tmp_path / 'output'

    failed = HistoricalQuotesB3().extract(
        path_of_docs=str(sources),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(destination),
        processing_mode=mode,
        verbose=False,
    )

    assert failed['success'] is False
    error = failed['errors'][original.name]
    assert 'line=2' in error
    assert 'field=record_length' in error
    assert "value='246'" in error
    assert 'UTF-8' in error
    assert 'separate Latin-1 copy' in error
    assert not destination.exists()
    assert original.read_bytes() == original_bytes

    normalized_sources = tmp_path / 'normalized'
    normalized_sources.mkdir()
    normalized = normalized_sources / original.name
    normalized_payload = text.encode('latin-1')
    if extension == 'ZIP':
        write_zip(normalized, {'COTAHIST_A2024.TXT': normalized_payload})
    else:
        normalized.write_bytes(normalized_payload)

    recovered = HistoricalQuotesB3().extract(
        path_of_docs=str(normalized_sources),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(destination),
        processing_mode=mode,
        verbose=False,
    )

    assert recovered['success'] is True
    assert recovered['total_records'] == (2 if market == '010' else 1)
    rows = pq.read_table(recovered['output_file']).to_pylist()
    expected = quote if market == '010' else build_cotahist_record()
    assert rows[0]['nome_resumido'] == expected[27:39].strip()
    assert rows[0]['registro_original'] == expected.encode('latin-1')
    assert original.read_bytes() == original_bytes


@pytest.mark.parametrize(
    'payload',
    [
        build_cotahist_record().encode('latin-1') + b'\xff',
        _replace(build_cotahist_record(), 27, 39, 'FROTA NAV€GA').encode(
            'utf-8'
        ),
    ],
    ids=['invalid-utf8', 'not-latin1'],
)
def test_encoding_hint_requires_lossless_latin1_conversion(
    tmp_path: Path, payload: bytes
) -> None:
    """Other width errors must not suggest an invalid encoding conversion."""
    source = tmp_path / 'COTAHIST_A2024.TXT'
    source.write_bytes(
        build_cotahist_header(2024).encode('ascii') + b'\n' + payload + b'\n'
    )
    destination = tmp_path / 'output'

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(destination),
        verbose=False,
    )

    assert result['success'] is False
    error = result['errors'][source.name]
    assert 'field=record_length' in error
    assert 'Expected exactly 245 bytes' in error
    assert 'separate Latin-1 copy' not in error
    assert not destination.exists()
