#!/usr/bin/env python3
"""Structurally validate root or local AGENTS.md guidance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = 'agents-md-policy.v3'
VALIDATION_KIND = 'structural'
ROOT_SECTIONS = (
    'Project Overview',
    'Architecture & Ownership',
    'Development Workflow',
    'Engineering Rules',
    'Documentation Map',
)
PROSE_PLACEHOLDER_PATTERNS = (
    r'\b(?:TODO|TBD|FIXME)\b',
    r'\bYYYY-MM-DD\b',
)
AUTHORSHIP_PLACEHOLDER_PATTERNS = (
    r'\[PROJECT_NAME\]',
    r'\{\{\s*[^}]+\s*\}\}',
    r'<(?:fill|replace|preencher|project(?: name)?|todo|owner|date)[^>]*>',
    r'AGENTS_AUTHOR',
)
INLINE_LINK_RE = re.compile(
    r'!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|(?:\\.|[^\s)]+))'
    r'(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?\s*\)'
)
REFERENCE_LINK_RE = re.compile(
    r'^\s{0,3}\[[^\]]+\]:\s*(<[^>\n]+>|(?:\\.|[^\s]+))'
)
INLINE_CODE_RE = re.compile(r'(?<!`)(`+)(?!`)([^\n]*?)\1(?!`)')
HTML_COMMENT_RE = re.compile(r'<!--.*?-->', flags=re.DOTALL)
EMPTY_MARKUP_RE = re.compile(r'(?:[-*+]|\d+[.)]|#{1,6})\s*')


def _has_content(text: str) -> bool:
    without_comments = HTML_COMMENT_RE.sub('', text)
    return any(
        line.strip() and not EMPTY_MARKUP_RE.fullmatch(line.strip())
        for line in without_comments.splitlines()
    )


def _visible_lines(text: str) -> list[str]:
    """Return lines outside fenced code blocks in one linear scan."""
    result: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in text.splitlines():
        stripped = line.lstrip()
        match = re.match(r'^(`{3,}|~{3,})', stripped)
        if match:
            marker = match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None:
            result.append(line)

    return result


def _headings(lines: list[str]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line in lines:
        match = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
        if match:
            result.append((len(match.group(1)), match.group(2)))
    return result


def _root_sections(lines: list[str]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    name: str | None = None
    content: list[str] = []

    for line in lines:
        match = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
        if match and len(match.group(1)) <= 2:
            if name is not None:
                visible = HTML_COMMENT_RE.sub('', '\n'.join(content)).strip()
                sections.append((name, visible))
            name = match.group(2) if len(match.group(1)) == 2 else None
            content = []
        elif name is not None:
            content.append(line)

    if name is not None:
        visible = HTML_COMMENT_RE.sub('', '\n'.join(content)).strip()
        sections.append((name, visible))
    return sections


def _check_root_sections(lines: list[str]) -> list[str]:
    content = HTML_COMMENT_RE.sub('', '\n'.join(lines))
    sections = _root_sections(content.splitlines())
    names = [name for name, _ in sections]
    errors: list[str] = []

    if len(sections) < len(ROOT_SECTIONS):
        errors.append(
            'root document requires at least five level-two sections '
            f'(found {len(sections)})'
        )

    seen: set[str] = set()
    for name, content in sections:
        if name in seen:
            errors.append(f'duplicate root section: {name}')
        seen.add(name)
        if not _has_content(content):
            errors.append(f'root section is empty: {name}')

    if all(name in names for name in ROOT_SECTIONS) and [
        names.index(name) for name in ROOT_SECTIONS
    ] != sorted(names.index(name) for name in ROOT_SECTIONS):
        errors.append(
            'standard root sections must appear in order: '
            + ', '.join(ROOT_SECTIONS)
        )
    return errors


def _check_placeholders(text: str) -> list[str]:
    """Allow inline literals while retaining explicit scaffold markers."""
    prose = INLINE_CODE_RE.sub('', text)
    return [
        f'unresolved authorship marker found: {pattern}'
        for source, patterns in (
            (prose, PROSE_PLACEHOLDER_PATTERNS),
            (text, AUTHORSHIP_PLACEHOLDER_PATTERNS),
        )
        for pattern in patterns
        if re.search(pattern, source, flags=re.IGNORECASE)
    ]


def _link_destinations(lines: list[str]) -> list[str]:
    destinations: list[str] = []
    for line in lines:
        without_code = INLINE_CODE_RE.sub('', line)
        destinations.extend(
            match.group(1) for match in INLINE_LINK_RE.finditer(without_code)
        )
        reference = REFERENCE_LINK_RE.match(without_code)
        if reference:
            destinations.append(reference.group(1))
    return destinations


def _relative_path(destination: str, base_dir: Path) -> Path | None:
    target = destination[1:-1] if destination.startswith('<') else destination
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.path.startswith('/'):
        return None
    relative_target = unquote(parsed.path)
    if not relative_target:
        return None
    return (base_dir / relative_target).resolve()


def _check_relative_links(lines: list[str], base_dir: Path) -> list[str]:
    errors: list[str] = []
    for destination in _link_destinations(lines):
        try:
            target = _relative_path(destination, base_dir)
            if target is not None and not target.exists():
                errors.append(f'broken relative Markdown link: {destination}')
        except ValueError:
            errors.append(f'invalid Markdown link destination: {destination}')
        except (OSError, RuntimeError):
            errors.append(f'broken relative Markdown link: {destination}')
    return errors


def validate(
    text: str,
    *,
    scope: str = 'root',
    base_dir: Path | None = None,
) -> list[str]:
    """Return structural violations for a root or local guidance file."""
    lines = _visible_lines(text)
    visible_text = '\n'.join(lines)
    errors: list[str] = []

    if scope not in {'root', 'local'}:
        errors.append(f'unsupported validation scope: {scope}')
    elif not _has_content(text):
        errors.append('document must not be empty')
    elif scope == 'root':
        errors.extend(_check_root_sections(lines))

    errors.extend(_check_placeholders(visible_text))
    errors.extend(_check_relative_links(lines, base_dir or Path.cwd()))
    return errors


def _payload(
    path: Path,
    errors: list[str],
    *,
    scope: str,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'status': status or ('passed' if not errors else 'failed'),
        'file': str(path),
        'scope': scope,
        'validation_kind': VALIDATION_KIND,
        'errors': errors,
    }


def _render_text(payload: dict[str, Any]) -> str:
    status = str(payload['status']).upper()
    scope = str(payload['scope'])
    path = str(payload['file'])
    lines = [f'{status} ({scope}, structural): {path}']
    lines.extend(f'- {error}' for error in payload['errors'])
    if 'size' in payload:
        size = payload['size']
        lines.append(
            f'Size: {size["utf8_bytes"]} UTF-8 bytes, {size["lines"]} lines'
        )
        lines.extend(f'WARNING: {warning}' for warning in payload['warnings'])
    return '\n'.join(lines)


def _add_size_report(
    payload: dict[str, Any], text: str, data: bytes, max_bytes: int | None
) -> None:
    """Report this file's size without claiming client-chain validation."""
    byte_count = len(data)
    payload['size'] = {
        'utf8_bytes': byte_count,
        'lines': len(text.splitlines()),
        'max_bytes': max_bytes,
    }
    payload['warnings'] = (
        [
            f'document uses {byte_count} UTF-8 bytes, exceeding the '
            f'configured per-file budget of {max_bytes} bytes; '
            'instruction-chain loading was not checked'
        ]
        if max_bytes is not None and byte_count > max_bytes
        else []
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(
        description='Structurally validate root or local AGENTS.md guidance.'
    )
    parser.add_argument(
        '--file',
        type=Path,
        default=Path('AGENTS.md'),
        help='AGENTS.md path to validate (default: AGENTS.md)',
    )
    parser.add_argument(
        '--scope',
        choices=('root', 'local'),
        default='root',
        help='validation scope (default: root)',
    )
    parser.add_argument(
        '--format',
        choices=('text', 'json'),
        default='text',
        help='output format (default: text)',
    )
    parser.add_argument(
        '--size-report',
        action='store_true',
        help='Report UTF-8 bytes and lines without imposing a size limit.',
    )
    parser.add_argument(
        '--max-bytes',
        type=int,
        help='Warn above this positive per-file byte budget; implies --size-report.',
    )
    args = parser.parse_args()
    if args.max_bytes is not None and args.max_bytes <= 0:
        parser.error('--max-bytes must be greater than zero')

    try:
        data = args.file.read_bytes()
        text = data.decode('utf-8')
    except (OSError, UnicodeError) as exc:
        payload = _payload(
            args.file,
            [str(exc)],
            scope=args.scope,
            status='error',
        )
        if args.format == 'json':
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(_render_text(payload), file=sys.stderr)
        return 2

    errors = validate(
        text,
        scope=args.scope,
        base_dir=args.file.resolve().parent,
    )
    payload = _payload(args.file, errors, scope=args.scope)
    if args.size_report or args.max_bytes is not None:
        _add_size_report(payload, text, data, args.max_bytes)
    if args.format == 'json':
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(_render_text(payload))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
