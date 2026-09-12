"""Encoding and strict CSV parsing regressions for ZIP members."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra import ReadFilesAdapter
from tests.support.builders import csv_bytes, write_zip

pytestmark = pytest.mark.integration
# allow-assertion-reduction: Codec cases are consolidated.


@pytest.mark.parametrize(
    ('content', 'expected_encoding'),
    [
        (csv_bytes(['texto', 'Mãe'], encoding='utf-8'), 'utf-8'),
        (
            csv_bytes(['texto', 'Mãe'], encoding='utf-8', bom=True),
            'utf-8-sig',
        ),
        (csv_bytes(['texto', 'Preço €'], encoding='cp1252'), 'cp1252'),
        (b'texto\nA\x81\n', 'latin-1'),
    ],
)
def test_encoding_detection_validates_complete_member_with_precedence(
    tmp_path: Path,
    content: bytes,
    expected_encoding: str,
) -> None:
    """The supported codecs preserve the intended deterministic precedence."""
    archive_path = write_zip(tmp_path / 'encoding.zip', {'data.csv': content})

    with zipfile.ZipFile(archive_path) as archive:
        detected = ReadFilesAdapter.read_csv_test_encoding(archive, 'data.csv')

    assert detected == expected_encoding


def test_encoding_detection_scans_beyond_the_historical_ten_kib_sample(
    tmp_path: Path,
) -> None:
    """Late UTF-8 text cannot become Latin-1 after an ASCII prefix."""
    ascii_prefix = 'x' * 11_000
    content = csv_bytes(['texto', f'{ascii_prefix} Mãe São Paulo'])
    archive_path = write_zip(
        tmp_path / 'late-accent.zip', {'data.csv': content}
    )

    with zipfile.ZipFile(archive_path) as archive:
        detected = ReadFilesAdapter.read_csv_test_encoding(archive, 'data.csv')

    assert detected == 'utf-8'


def test_encoding_detection_does_not_use_csv_parser_as_a_codec_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parser failure cannot trigger a fallback encoding choice."""
    archive_path = write_zip(
        tmp_path / 'separate-concerns.zip',
        {'data.csv': csv_bytes(['a;b', '1;2;3'])},
    )

    def fail_parser(*_args: object, **_kwargs: object) -> object:
        raise AssertionError('encoding detection must not parse CSV rows')

    monkeypatch.setattr(pd, 'read_csv', fail_parser)

    with zipfile.ZipFile(archive_path) as archive:
        detected = ReadFilesAdapter.read_csv_test_encoding(archive, 'data.csv')

    assert detected == 'utf-8'


def test_utf8_bom_with_invalid_bytes_fails_closed(tmp_path: Path) -> None:
    """A BOM asserts UTF-8 and cannot be silently reinterpreted as Latin-1."""
    archive_path = write_zip(
        tmp_path / 'invalid-bom.zip',
        {'data.csv': b'\xef\xbb\xbftexto\n\xff\n'},
    )

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(ExtractionError, match='BOM is present'),
    ):
        ReadFilesAdapter.read_csv_test_encoding(archive, 'data.csv')


def test_csv_chunk_reader_fails_on_structurally_malformed_rows() -> None:
    """Malformed CSV rows abort extraction instead of being skipped."""
    malformed = io.StringIO('first;second\n1;2\n1;2;3;4;5\n')

    with pytest.raises(pd.errors.ParserError):
        list(ReadFilesAdapter.read_csv_chunk_size(malformed, chunk_size=2))


def test_csv_chunk_reader_preserves_unescaped_quotes_as_literals() -> None:
    """Unescaped quotation marks in text are preserved as literal text."""
    stream = io.StringIO('nome;descricao\nEmpresa;"Texto com "aspas" livres\n')
    chunks = list(ReadFilesAdapter.read_csv_chunk_size(stream, chunk_size=10))
    assert len(chunks) == 1
    assert chunks[0]['descricao'].iloc[0] == '"Texto com "aspas" livres'
