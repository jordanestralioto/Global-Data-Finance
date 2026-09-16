"""Best-effort redaction for structured library log output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from logging import LogRecord
from typing import Any

REDACTED = '[REDACTED]'

_SENSITIVE_KEY_RE = re.compile(
    r'(?:^|[_-])(?:access[_-]?token|api[_-]?key|auth|authorization|'
    r'client[_-]?secret|cookie|credential|password|passwd|private[_-]?key|'
    r'refresh[_-]?token|secret|signature|token)(?:$|[_-])',
    re.IGNORECASE,
)
_URL_SECRET_RE = re.compile(
    r'([?&](?:access[_-]?token|api[_-]?key|auth|authorization|'
    r'cookie|password|passwd|secret|signature|token)=)[^&#\s|]+',
    re.IGNORECASE,
)
_KEY_VALUE_SECRET_RE = re.compile(
    r'(\b(?:access[_-]?token|api[_-]?key|auth|authorization|cookie|'
    r'password|passwd|private[_-]?key|refresh[_-]?token|secret|signature|'
    r'token)\b\s*[:=]\s*)[^\r\n,;|}]+',
    re.IGNORECASE,
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
    """Redact common URL-query and key/value secrets from text."""
    text = _URL_SECRET_RE.sub(rf'\1{REDACTED}', text)
    return _KEY_VALUE_SECRET_RE.sub(rf'\1{REDACTED}', text)


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
