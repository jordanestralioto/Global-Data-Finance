"""Keep console presentation text encodable by the active standard output.

Redirected Windows output commonly uses a legacy code page such as cp1252.
Presentation glyphs must degrade there instead of aborting an operation, and
the application's own ``sys.stdout`` configuration is never modified.
"""

import codecs
import sys


def _stdout_encoding() -> str:
    return getattr(sys.stdout, 'encoding', None) or 'utf-8'


def console_supports(text: str) -> bool:
    """Return whether standard output can encode ``text`` unchanged."""
    try:
        text.encode(_stdout_encoding())
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def console_text(text: str) -> str:
    """Replace only the characters standard output cannot encode."""
    if console_supports(text):
        return text
    try:
        encoding = codecs.lookup(_stdout_encoding()).name
    except LookupError:
        encoding = 'ascii'
    return text.encode(encoding, errors='replace').decode(encoding)


def print_console(text: str) -> None:
    """Write one presentation line that standard output can encode."""
    sys.stdout.write(f'{console_text(text)}\n')
