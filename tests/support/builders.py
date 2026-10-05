"""Deterministic builders for archive and COTAHIST regression tests."""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path


def build_cotahist_record(
    *,
    year: int = 2024,
    ticker: str = 'PETR4',
    market: str = '010',
    trailing_spaces: int = 0,
) -> str:
    """Build one complete 245-character COTAHIST type-01 quote record."""
    line = [' '] * 245
    _put_text(line, 0, 2, '01')
    _put_text(line, 2, 10, f'{year}0115')
    _put_text(line, 10, 12, '02')
    _put_text(line, 12, 24, ticker)
    _put_text(line, 24, 27, market)
    _put_text(line, 27, 39, 'PETROBRAS')
    _put_text(line, 39, 49, 'ON')
    for start, end in (
        (56, 69),
        (69, 82),
        (82, 95),
        (95, 108),
        (108, 121),
        (121, 134),
        (134, 147),
    ):
        _put_number(line, start, end, 12_345)
    _put_number(line, 147, 152, 1)
    _put_number(line, 152, 170, 100)
    _put_number(line, 170, 188, 123_456)
    _put_number(line, 188, 201, 0)
    _put_text(line, 201, 202, '0')
    _put_text(line, 202, 210, f'{year}1231')
    _put_number(line, 210, 217, 1)
    _put_number(line, 217, 230, 0)
    _put_text(line, 230, 242, 'BRPETRACNPR6')
    _put_number(line, 242, 245, 1)
    record = ''.join(line)
    assert len(record) == 245
    return record + (' ' * trailing_spaces)


def build_b3_typed_record(
    *,
    ticker: str = 'PETR4',
    price: Decimal = Decimal('123.45'),
    original_record: bytes = bytes(245),
    source_line: int = 1,
) -> dict[str, object]:
    """Build one fully populated version 2 logical writer row."""
    return {
        'data_pregao': date(2024, 1, 15),
        'codigo_bdi': '02',
        'ticker': ticker,
        'tipo_mercado': '010',
        'nome_resumido': 'PETROBRAS',
        'especificacao_papel': 'ON',
        'preco_abertura': price,
        'preco_maximo': price,
        'preco_minimo': price,
        'preco_medio': price,
        'preco_fechamento': price,
        'melhor_oferta_compra': price,
        'melhor_oferta_venda': price,
        'numero_negocios': 1,
        'quantidade_total': 100,
        'volume_total': Decimal('1234.56'),
        'data_vencimento': date(2024, 12, 31),
        'fator_cotacao': 1,
        'codigo_isin': 'BRPETRACNPR6',
        'numero_distribuicao': 1,
        'prazo_termo': '',
        'moeda_referencia': '',
        'preco_exercicio': Decimal('0.00'),
        'indicador_correcao': '0',
        'preco_exercicio_pontos': Decimal('0.000000'),
        'tipo_registro': '01',
        'id_fonte': hashlib.sha256(b'cotahist-test-source').hexdigest(),
        'arquivo_origem': 'COTAHIST_A2024.TXT',
        'membro_origem': '',
        'ano_origem': 2024,
        'linha_origem': source_line,
        'registro_original': original_record,
    }


def build_cotahist_header(
    year: int,
    *,
    generation_date: date | None = None,
) -> str:
    """Build one official fixed-width COTAHIST header control."""
    generated = generation_date or date(year, 12, 31)
    line = [' '] * 245
    _put_text(line, 0, 2, '00')
    _put_text(line, 2, 15, f'COTAHIST.{year:04d}')
    _put_text(line, 15, 23, 'BOVESPA')
    _put_text(line, 23, 31, generated.strftime('%Y%m%d'))
    return ''.join(line)


def build_cotahist_trailer(
    year: int,
    quote_count: int,
    *,
    generation_date: date | None = None,
    count_convention: str = 'quotes_and_controls',
) -> str:
    """Build a valid trailer using one of the two supported count rules."""
    generated = generation_date or date(year, 12, 31)
    if count_convention == 'quotes_and_controls':
        declared_count = quote_count + 2
    elif count_convention == 'quotes_only':
        declared_count = quote_count
    else:
        raise ValueError(f'Unsupported trailer convention: {count_convention}')
    line = [' '] * 245
    _put_text(line, 0, 2, '99')
    _put_text(line, 2, 15, f'COTAHIST.{year:04d}')
    _put_text(line, 15, 23, 'BOVESPA')
    _put_text(line, 23, 31, generated.strftime('%Y%m%d'))
    _put_number(line, 31, 42, declared_count)
    return ''.join(line)


def build_long_cotahist_line(byte_length: int) -> bytes:
    """Build deterministic incompressible bytes without line terminators."""
    line = hashlib.shake_256(b'long-cotahist-line-fixture').digest(byte_length)
    return line.replace(b'\r', b'R').replace(b'\n', b'N')


def write_cotahist_zip(
    directory: Path,
    *,
    year: int,
    records: Iterable[str],
    historical_member: bool = False,
    member_name: str | None = None,
    extra_members: Mapping[str, bytes | str] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
    generation_date: date | None = None,
    trailer_convention: str = 'quotes_and_controls',
) -> Path:
    """Write an official archive with a selectable member-name layout."""
    archive_path = directory / f'COTAHIST_A{year}.ZIP'
    member_name = member_name or (
        f'COTAHIST.A{year}' if historical_member else f'COTAHIST_A{year}.TXT'
    )
    quote_records = list(records)
    controls = [
        build_cotahist_header(year, generation_date=generation_date),
        *quote_records,
        build_cotahist_trailer(
            year,
            len(quote_records),
            generation_date=generation_date,
            count_convention=trailer_convention,
        ),
    ]
    payload = ('\n'.join(controls) + '\n').encode('latin-1')
    with zipfile.ZipFile(archive_path, 'w', compression) as archive:
        archive.writestr(member_name, payload)
        for name, content in (extra_members or {}).items():
            archive.writestr(name, content)
    return archive_path


def write_cotahist_txt(
    directory: Path,
    *,
    year: int,
    records: Iterable[str],
    generation_date: date | None = None,
    trailer_convention: str = 'quotes_and_controls',
) -> Path:
    """Write one official plain-text COTAHIST input."""
    txt_path = directory / f'COTAHIST_A{year}.TXT'
    quote_records = list(records)
    controls = [
        build_cotahist_header(year, generation_date=generation_date),
        *quote_records,
        build_cotahist_trailer(
            year,
            len(quote_records),
            generation_date=generation_date,
            count_convention=trailer_convention,
        ),
    ]
    txt_path.write_bytes(('\n'.join(controls) + '\n').encode('latin-1'))
    return txt_path


def write_zip(
    archive_path: Path,
    members: Mapping[str, bytes | str],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    """Write a compact ZIP archive with caller-defined member bytes."""
    with zipfile.ZipFile(archive_path, 'w', compression) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return archive_path


def csv_bytes(
    rows: Iterable[str],
    *,
    encoding: str = 'utf-8',
    bom: bool = False,
) -> bytes:
    """Encode delimiter-separated CSV rows with an optional UTF-8 BOM."""
    content = '\n'.join(rows) + '\n'
    prefix = b'\xef\xbb\xbf' if bom else b''
    return prefix + content.encode(encoding)


def _put_text(line: list[str], start: int, end: int, value: str) -> None:
    width = end - start
    assert len(value) <= width
    line[start:end] = list(value.ljust(width))


def _put_number(line: list[str], start: int, end: int, value: int) -> None:
    _put_text(line, start, end, str(value).rjust(end - start, '0'))
