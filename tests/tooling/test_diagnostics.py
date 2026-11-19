"""Redaction and bounds of diagnostics that gates copy from external tools."""

from __future__ import annotations

import secrets

import pytest

from scripts.diagnostics import (
    DIAGNOSTIC_LIMIT,
    REDACTED,
    redact_diagnostic,
    summarize_diagnostic,
)

pytestmark = pytest.mark.unit

SECRET = secrets.token_hex(12)


@pytest.mark.parametrize(
    'template',
    [
        'https://' + 'user:{secret}' + '@index.invalid/simple/',
        'https://' + '{secret}' + '@index.invalid/simple/',
        'https://index.invalid/simple/?access_token={secret}',
        'https://index.invalid/x?a=1&X-Amz-Signature={secret}&b=2',
        'https://blob.invalid/x?sv=2024&sig={secret}',
        'https://maps.invalid/api?key={secret}&q=1',
        'UV_INDEX_PASSWORD={secret} uv lock',
        'client_secret = {secret}',
        'Authorization: Basic {secret}',
        'Proxy-Authorization: Bearer {secret}',
        'request sent with Bearer {secret}',
    ],
    ids=[
        'url-userinfo',
        'url-token-userinfo',
        'query-token',
        'query-signature',
        'query-sas-signature',
        'query-api-key',
        'environment-assignment',
        'spaced-assignment',
        'authorization-header',
        'proxy-authorization-header',
        'bearer-credential',
    ],
)
def test_credential_shapes_are_masked(template: str) -> None:
    """Each supported credential shape loses its value, not its context."""
    redacted = redact_diagnostic(template.format(secret=SECRET))

    assert SECRET not in redacted
    assert REDACTED in redacted


@pytest.mark.parametrize(
    'token',
    [
        'ghp_' + SECRET * 2,
        'github_pat_' + SECRET * 2,
        'glpat-' + SECRET * 2,
        'pypi-' + SECRET * 2,
        'AKIA' + SECRET[:16].upper(),
        f'eyJ{SECRET}.{SECRET}.{SECRET}',
    ],
    ids=['github', 'github-fine-grained', 'gitlab', 'pypi', 'aws', 'jwt'],
)
def test_known_token_formats_are_masked_anywhere(token: str) -> None:
    """A recognizable token is masked even without a credential label."""
    redacted = redact_diagnostic(f'error: rejected {token} for the index')

    assert redacted == f'error: rejected {REDACTED} for the index'


@pytest.mark.parametrize(
    'diagnostic',
    [
        'error: No solution found when resolving dependencies',
        'hint: pass --keyring-provider=subprocess to read credentials',
        'Caused by: failed to lookup address information',
    ],
)
def test_ordinary_diagnostics_are_unchanged(diagnostic: str) -> None:
    """Redaction does not hide the cause of an ordinary failure."""
    assert redact_diagnostic(diagnostic) == diagnostic


def test_long_diagnostics_keep_both_ends_within_the_limit() -> None:
    """The failed operation and the root cause both survive the bound."""
    first = 'error: Failed to fetch: https://index.invalid/simple/example/'
    last = 'Caused by: dns error: failed to lookup address information'
    text = '\n'.join([first, *['  Caused by: request retried'] * 300, last])

    summary = summarize_diagnostic(text)

    assert len(summary) == DIAGNOSTIC_LIMIT
    assert summary.startswith(first)
    assert summary.endswith(last)
    assert '\n' not in summary


def test_redaction_happens_before_truncation() -> None:
    """A credential that straddles the cut is never partially printed."""
    text = (
        'x' * 150
        + ' https://index.invalid/?access_token='
        + SECRET * 30
        + ' '
        + 'y' * 600
    )

    summary = summarize_diagnostic(text)

    assert len(summary) == DIAGNOSTIC_LIMIT
    assert SECRET[:8] not in summary


@pytest.mark.parametrize('text', ['', '   \n\n  '])
def test_empty_diagnostics_summarize_to_nothing(text: str) -> None:
    """Callers can fall back to their own message for empty output."""
    assert summarize_diagnostic(text) == ''
