"""Formatted URL, JSON, and exception text must redact synthetic secrets."""

from __future__ import annotations

import json
import logging
import multiprocessing
from multiprocessing.connection import Connection

import httpx
import pytest

from globaldatafinance.core.logging_config import StructuredFormatter

pytestmark = pytest.mark.unit


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        'redaction-test', logging.INFO, __file__, 1, message, args, None
    )


@pytest.mark.parametrize(
    'key',
    [
        'key',
        'KEY',
        'api_key',
        'token',
        'id_token',
        'auth_token',
        'session-token',
        'code',
        'state',
        '%63ode',
        '%73tate',
        '%6bey',
        '%61pi_key',
        'api%5Fkey',
        'api%2Dkey',
    ],
)
def test_url_secrets_preserve_adjacent_public_parameters(key: str) -> None:
    """Bare keys and named credentials are removed without losing the URL."""
    record = _record(
        'Download %s',
        f'https://example.test/archive?{key}=synthetic-value&year=2024',
    )

    formatted = StructuredFormatter('%(message)s').format(record)

    assert 'synthetic-value' not in formatted
    assert f'?{key}=[REDACTED]&year=2024' in formatted
    assert 'https://example.test/archive' in formatted


@pytest.mark.parametrize(
    'key',
    [
        'password',
        'api_key',
        'Authorization',
        'client_secret',
        'token',
        'id_token',
        'auth_token',
        'session-token',
        'private_key_id',
    ],
)
@pytest.mark.parametrize('value', ['synthetic-value', 'synthetic,;|}\\"value'])
def test_json_secret_fields_remain_valid_json(key: str, value: str) -> None:
    """Quotes, escapes, and punctuation cannot expose the rest of a value."""
    record = _record(
        '%s', json.dumps({key: value, 'phase': 'download', 'rows': 2})
    )

    formatted = StructuredFormatter('%(message)s').format(record)

    assert 'synthetic' not in formatted
    assert json.loads(formatted) == {
        key: '[REDACTED]',
        'phase': 'download',
        'rows': 2,
    }


def test_single_quoted_fields_in_message_context_are_redacted() -> None:
    """A serialized mapping inside ordinary log context receives redaction."""
    record = _record('Processing download')
    record.extra_data = {
        'payload': (
            "{'password': 'synthetic-value', "  # pragma: allowlist secret
            "'rows': 2}"
        ),
        'phase': 'download',
    }

    formatted = StructuredFormatter('%(message)s').format(record)

    assert 'synthetic-value' not in formatted
    assert "'password': '[REDACTED]'" in formatted
    assert "'rows': 2" in formatted
    assert 'phase=download' in formatted


def test_exception_json_and_url_values_are_redacted() -> None:
    """Traceback formatting applies the same protection as message text."""
    exception = ValueError(
        '{"password": "synthetic-password", '  # pragma: allowlist secret
        '"url": "https://example.test?key=synthetic-key&year=2024"}'
    )
    record = _record('Download failed')
    record.exc_info = (ValueError, exception, None)

    formatted = StructuredFormatter('%(message)s').format(record)

    assert 'synthetic-password' not in formatted
    assert 'synthetic-key' not in formatted
    assert 'ValueError' in formatted
    assert 'year=2024' in formatted


@pytest.mark.parametrize(
    'authority',
    [
        'user:synthetic-password@example.test',
        'synthetic-user@example.test',
        'user:synthetic%2Dpassword@[::1]:8443',
    ],
)
@pytest.mark.parametrize('scheme', ['https:', ''])
def test_http_status_error_redacts_url_user_info(
    authority: str, scheme: str
) -> None:
    """Request failures cannot persist URL usernames or passwords in logs."""
    response = httpx.Response(
        403,
        request=httpx.Request('GET', f'{scheme}//{authority}/file?year=2024'),
    )
    with pytest.raises(httpx.HTTPStatusError) as failure:
        response.raise_for_status()
    record = _record('Download failed: %s', str(failure.value))

    formatted = StructuredFormatter('%(message)s').format(record)

    assert 'synthetic' not in formatted.casefold()
    assert '[REDACTED]@' in formatted
    assert '/file?year=2024' in formatted


@pytest.mark.parametrize(
    'text',
    [
        'https://example.test/@public?year=2024',
        'https://example.test//public@part?year=2024',
        'contact public@example.test',
        'https://example.test/file?year=2024',
        'https://example.test/file?%79ear=2024',
    ],
)
def test_public_url_and_email_context_remains_readable(text: str) -> None:
    """An at sign outside URL authority does not remove useful context."""
    formatted = StructuredFormatter('%(message)s').format(_record(text))

    assert formatted == text


@pytest.mark.parametrize(
    'key', ['monkey', 'trace_id', 'tokenizer', 'public_key']
)
def test_ordinary_field_names_keep_their_values(key: str) -> None:
    """Sensitive components require field boundaries rather than substrings."""
    message = json.dumps({key: 'ordinary-value', 'rows': 2})

    formatted = StructuredFormatter('%(message)s').format(_record(message))

    assert formatted == message


def _format_in_worker(message: str, connection: Connection) -> None:
    """Isolate hostile regex input so a regression cannot hang pytest."""
    try:
        formatted = StructuredFormatter('%(message)s').format(_record(message))
        connection.send(formatted)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ('message', 'expected'),
    [
        ('../' + 'a-' * 32_766, '../' + 'a-' * 32_766),
        ('?a' * 32_766, '?a' * 32_766),
        (
            'a-' * 32_766 + 'password=synthetic-value, rows=2',
            'a-' * 32_766 + 'password=[REDACTED], rows=2',
        ),
        (
            'a-' * 32_766 + '://synthetic-user@example.test/file?year=2024',
            'a-' * 32_766 + '://[REDACTED]@example.test/file?year=2024',
        ),
    ],
    ids=[
        'zip-member',
        'incomplete-query',
        'long-secret-key',
        'long-url-scheme',
    ],
)
def test_hostile_log_text_finishes_without_losing_redaction(
    message: str, expected: str
) -> None:
    """ZIP-sized names finish within a generous process deadline."""
    context = multiprocessing.get_context('spawn')
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_format_in_worker, args=(message, writer))
    process.start()
    writer.close()
    try:
        assert reader.poll(10), 'redaction exceeded its process deadline'
        formatted = reader.recv()
        process.join(10)
        assert process.exitcode == 0
        assert formatted == expected
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        reader.close()
        process.close()


@pytest.mark.parametrize(
    ('message', 'expected'),
    [
        (
            'rows=2 password=synthetic-value',  # pragma: allowlist secret
            'rows=2 password=[REDACTED]',
        ),
        (
            'data={"password":"synthetic"}',  # pragma: allowlist secret
            'data={"password":"[REDACTED]"}',
        ),
        (
            'phase=download; -auth_token="synthetic-value"; rows=2',
            'phase=download; -auth_token="[REDACTED]"; rows=2',
        ),
    ],
)
def test_public_field_values_do_not_hide_following_secret_fields(
    message: str, expected: str
) -> None:
    """Scanning ordinary fields still reaches nested or adjacent secrets."""
    formatted = StructuredFormatter('%(message)s').format(_record(message))

    assert formatted == expected
