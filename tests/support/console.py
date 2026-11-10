"""Simulate the strict legacy code page of redirected Windows output."""

import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import patch

LEGACY_CODE_PAGE = 'cp1252'


@contextmanager
def legacy_code_page_stdout() -> Iterator[Callable[[], str]]:
    """Replace stdout with a strict cp1252 stream and expose its text."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(
        raw, encoding=LEGACY_CODE_PAGE, errors='strict', newline=''
    )

    def written() -> str:
        stream.flush()
        return raw.getvalue().decode(LEGACY_CODE_PAGE)

    with patch('sys.stdout', stream):
        yield written
