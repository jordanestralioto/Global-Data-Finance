"""Reject invalid annual documents before creating publication artifacts."""

from pathlib import Path

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
