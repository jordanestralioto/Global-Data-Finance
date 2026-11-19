"""Redact and bound the diagnostics that gates copy from external tools.

Package managers and auditors can echo index URLs, proxy settings, and request
headers in their errors. Gates print such output only through
``summarize_diagnostic``: it masks URL userinfo, credential-bearing parameters
and assignments, authorization headers, and well-known token formats, then
keeps at most ``DIAGNOSTIC_LIMIT`` characters. Redaction runs before the text
is cut, so truncation never exposes the unmasked part of a known credential.
"""

from __future__ import annotations

import re

DIAGNOSTIC_LIMIT = 400
REDACTED = '***'
_GAP = ' … '
_SEPARATOR = ' | '
_CREDENTIAL_NAME = (
    r'(?:[\w.-]*?(?:token|secret|passw(?:or)?d|pwd|credentials?|signature'
    r'|auth|session)[\w.-]*|[\w.-]*key|sig)'
)
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r'(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@'),
        rf'\g<1>{REDACTED}@',
    ),
    (
        re.compile(rf'(?i)([?&#;]{_CREDENTIAL_NAME}=)[^&#\s]+'),
        rf'\g<1>{REDACTED}',
    ),
    (
        re.compile(rf'(?i)(?<![\w.-])({_CREDENTIAL_NAME}\s*=\s*)[^\s&;,]+'),
        rf'\g<1>{REDACTED}',
    ),
    (
        re.compile(
            r'(?i)\b((?:proxy-)?authorization|x-api-key|api-key|cookie)'
            r'(\s*:\s*)\S.*'
        ),
        rf'\g<1>\g<2>{REDACTED}',
    ),
    (
        re.compile(r'(?i)\b(bearer|basic)\s+[\w.~+/=-]{8,}'),
        rf'\g<1> {REDACTED}',
    ),
    (
        re.compile(
            r'\b(?:gh[oprsu]_\w{20,}|github_pat_\w{20,}|glpat-[\w-]{20,}'
            r'|pypi-[\w-]{16,}|xox[abprs]-[\w-]{10,}|(?:AKIA|ASIA)[0-9A-Z]{16}'
            r'|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,})'
        ),
        REDACTED,
    ),
)


def redact_diagnostic(text: str) -> str:
    """Mask the credentials that external tools may echo in diagnostics."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def summarize_diagnostic(text: str, limit: int = DIAGNOSTIC_LIMIT) -> str:
    """Return a redacted, single-line summary of at most ``limit`` characters.

    The first line usually names the failed operation and the last lines the
    root cause, so a summary that must be cut keeps both of its ends.
    """
    lines = (
        ' '.join(line.split()) for line in redact_diagnostic(text).splitlines()
    )
    summary = _SEPARATOR.join(line for line in lines if line)
    if len(summary) <= limit:
        return summary
    head = (limit - len(_GAP)) // 2
    tail = limit - len(_GAP) - head
    return f'{summary[:head]}{_GAP}{summary[-tail:]}'
