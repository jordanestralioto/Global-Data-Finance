"""Unit coverage for incremental CVM source encoding detection."""

from __future__ import annotations

import codecs
import zipfile
from pathlib import Path

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    source,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.unit

ReopenableCsvSource = source.ReopenableCsvSource
detect_encoding = source.detect_encoding
text_source = source.text_source

_UNDEFINED_CP1252_BYTES = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})


def _source(tmp_path: Path, contents: bytes) -> ReopenableCsvSource:
    archive_path = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('source.csv', contents)
    return ReopenableCsvSource(archive_path, 'source.csv')


@pytest.mark.parametrize('byte_value', range(0x80, 0xA0))
def test_every_cp1252_control_range_byte_selects_lossless_fallback(
    tmp_path: Path,
    byte_value: int,
) -> None:
    source = _source(tmp_path, b'value\n' + bytes([byte_value]) + b'\n')

    plan = detect_encoding(source)

    expected = 'latin-1' if byte_value in _UNDEFINED_CP1252_BYTES else 'cp1252'
    assert plan.encoding == expected
    assert plan.needs_utf8_spool is True


def test_utf8_bom_is_reported_and_removed_by_the_text_source(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, codecs.BOM_UTF8 + 'value\ná\n'.encode())

    plan = detect_encoding(source)

    assert plan.encoding == 'utf-8'
    assert plan.has_utf8_bom is True
    assert plan.needs_utf8_spool is False
    with text_source(source, None, plan) as text:
        assert text.read() == 'value\ná\n'


def test_invalid_utf8_after_bom_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, codecs.BOM_UTF8 + b'value\n\xff\n')

    with pytest.raises(ExtractionError, match='BOM is present'):
        detect_encoding(source)


def test_utf8_sequence_split_across_scan_blocks_remains_valid(
    tmp_path: Path,
) -> None:
    header = b'value\n'
    contents = (
        header + b'a' * (64 * 1024 - len(header) - 1) + '€'.encode() + b'\n'
    )
    source = _source(tmp_path, contents)

    plan = detect_encoding(source)

    assert plan.encoding == 'utf-8'
    assert plan.needs_utf8_spool is False


@pytest.mark.parametrize(
    ('invalid_bytes', 'expected_encoding'),
    [
        (b'\xff', 'latin-1'),
        (b'\xc3(', 'latin-1'),
        (b'\x82', 'cp1252'),
        (b'\xe2\x82', 'cp1252'),
    ],
)
def test_invalid_utf8_sequences_keep_the_existing_fallback_policy(
    tmp_path: Path,
    invalid_bytes: bytes,
    expected_encoding: str,
) -> None:
    source = _source(tmp_path, b'value\n' + invalid_bytes + b'\n')

    plan = detect_encoding(source)

    assert plan.encoding == expected_encoding
    assert plan.needs_utf8_spool is True


def test_undefined_cp1252_byte_takes_precedence_in_mixed_input(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, b'value\n\x80\x81\n')

    plan = detect_encoding(source)

    assert plan.encoding == 'latin-1'


def test_empty_csv_member_is_valid_for_encoding_detection(
    tmp_path: Path,
) -> None:
    plan = detect_encoding(_source(tmp_path, b''))

    assert plan.encoding == 'utf-8'
    assert plan.has_utf8_bom is False
    assert plan.needs_utf8_spool is False
