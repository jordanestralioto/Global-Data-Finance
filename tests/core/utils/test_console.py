"""Console text degrades instead of failing on a legacy code page."""

import io
from unittest.mock import patch

import pytest

from globaldatafinance.core.utils.console import (
    console_supports,
    console_text,
    print_console,
)
from tests.support.console import legacy_code_page_stdout

pytestmark = pytest.mark.unit


def test_legacy_code_page_replaces_only_unencodable_characters() -> None:
    """Accented text survives while unsupported symbols become markers."""
    with legacy_code_page_stdout():
        assert not console_supports('📊 ✓')
        assert console_text('📊 ✓ ação 100%') == '? ? ação 100%'


def test_utf8_output_keeps_presentation_text_unchanged() -> None:
    """Capable consoles keep the original glyphs."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
    with patch('sys.stdout', stream):
        assert console_supports('📊 █ ✓')
        assert console_text('📊 █ ✓') == '📊 █ ✓'


def test_stream_without_encoding_is_treated_as_unicode() -> None:
    """In-memory replacements such as StringIO accept any text."""
    with patch('sys.stdout', new_callable=io.StringIO) as stream:
        print_console('📊 B3')

    assert stream.getvalue() == '📊 B3\n'


def test_unknown_stream_encoding_falls_back_to_ascii() -> None:
    """An unusable encoding name cannot abort presentation output."""

    class UnknownEncodingStream(io.StringIO):
        encoding = 'not-a-real-codec'

    with patch('sys.stdout', new_callable=UnknownEncodingStream):
        assert not console_supports('a')
        assert console_text('ação ✓') == 'a??o ?'


def test_print_console_writes_encodable_line_to_legacy_stdout() -> None:
    """Printing through the helper never raises UnicodeEncodeError."""
    with legacy_code_page_stdout() as written:
        print_console('📥 download ✓')

    assert written() == '? download ?\n'
