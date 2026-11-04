"""Best-effort redaction for structured library log output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from logging import LogRecord
from typing import Any
from urllib.parse import unquote_plus

REDACTED = '[REDACTED]'

_SENSITIVE_FIELD = (
    r'(?:access[_-]?token|api[_-]?key|auth|authorization|'
    r'client[_-]?secret|cookie|credential|password|passwd|private[_-]?key|'
    r'refresh[_-]?token|secret|signature|token)'
)
_SENSITIVE_KEY_RE = re.compile(
    rf'(?:^|[_-]){_SENSITIVE_FIELD}(?:$|[_-])',
    re.IGNORECASE,
)
_URL_USERINFO_RE = re.compile(
    r"""((?::|(?<![\w/.:]))//)[^/\s?#"'<>]*@""",
)
_URL_QUERY_RE = re.compile(
    r"""(?P<prefix>[?&](?P<key>[^=?&#\s|"'<>]+)=)[^&#\s|"'<>]+""",
)
_FIELD_PREFIX_RE = re.compile(
    r"""(?<![\w-])(?P<key>[\w-]++)["']?\s*[:=]\s*""",
)
_SECRET_VALUE_RE = re.compile(
    r"""(?P<value>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\r\n,;|}&]+)""",
)
_STANDARD_RECORD_ATTRS: frozenset[str] = frozenset(
    (
        'args',
        'asctime',
        'created',
        'exc_info',
        'exc_text',
        'extra_data',
        'filename',
        'funcName',
        'levelname',
        'levelno',
        'lineno',
        'message',
        'module',
        'msecs',
        'msg',
        'name',
        'pathname',
        'process',
        'processName',
        'relativeCreated',
        'stack_info',
        'taskName',
        'thread',
        'threadName',
    )
)


def redact_log_text(text: str) -> str:
    """Redact URL credentials and common query and key/value secrets."""
    text = _URL_USERINFO_RE.sub(rf'\1{REDACTED}@', text)
    text = _URL_QUERY_RE.sub(_redact_query_value, text)
    return _redact_secret_fields(text)


def _redact_secret_fields(text: str) -> str:
    """Scan each field name once and consume values only for secret keys."""
    pieces: list[str] = []
    copied_until = 0
    search_from = 0
    while prefix := _FIELD_PREFIX_RE.search(text, search_from):
        search_from = prefix.end()
        if not _SENSITIVE_KEY_RE.search(prefix['key']):
            continue
        value = _SECRET_VALUE_RE.match(text, search_from)
        if value is None:
            continue
        pieces.extend(
            (text[copied_until : value.start()], _redact_field(value))
        )
        copied_until = search_from = value.end()
    pieces.append(text[copied_until:])
    return ''.join(pieces)


def _redact_query_value(match: re.Match[str]) -> str:
    key = unquote_plus(match['key'])
    if key.casefold() in {'key', 'code', 'state'} or _SENSITIVE_KEY_RE.search(
        key
    ):
        return f'{match["prefix"]}{REDACTED}'
    return match[0]


def _redact_field(match: re.Match[str]) -> str:
    value = match['value']
    quote = value[0] if value.startswith(('"', "'")) else ''
    return f'{quote}{REDACTED}{quote}'


def redact_log_value(key: str, value: Any) -> str:
    """Render one context value while redacting sensitive fields."""
    if _SENSITIVE_KEY_RE.search(key):
        return REDACTED
    return _render_value(value)


def format_structured_message(message: str, record: LogRecord) -> str:
    """Append safe record context to a formatter-generated message."""
    extra_items: dict[str, str] = {}
    extra_data = getattr(record, 'extra_data', None)
    if isinstance(extra_data, Mapping):
        extra_items.update(
            {
                str(key): redact_log_value(str(key), value)
                for key, value in extra_data.items()
            }
        )

    for attr, value in record.__dict__.items():
        if not attr.startswith('_') and attr not in _STANDARD_RECORD_ATTRS:
            extra_items[attr] = redact_log_value(attr, value)

    if extra_items:
        extra_str = ' | '.join(
            f'{key}={value}' for key, value in extra_items.items()
        )
        message = f'{message} | {extra_str}'
    return redact_log_text(message)


def _render_value(value: Any) -> str:
    if isinstance(value, Mapping):
        rendered = ', '.join(
            f'{key}={redact_log_value(str(key), nested)}'
            for key, nested in value.items()
        )
        return f'{{{rendered}}}'
    if isinstance(value, (list, tuple, set, frozenset)):
        return '[' + ', '.join(_render_value(item) for item in value) + ']'
    return redact_log_text(str(value))
