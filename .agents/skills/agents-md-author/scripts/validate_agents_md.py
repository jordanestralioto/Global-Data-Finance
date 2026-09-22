#!/usr/bin/env python3
"""Validate AGENTS.md against the portable structure and policy contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_TOP_LEVEL = (
    'System Overview',
    'Success Metrics',
    'Pipeline Architecture',
    'Configuration & Runtime',
    'Technical Stack',
    'Mandatory Rules',
    'Execution Policy',
    'Related Documentation',
)

EXPECTED_EXECUTION_SUBHEADINGS = (
    'Precedence',
    'Secrets',
    'Repo Alignment',
    'Autonomy',
    'Validation',
    'Execution Safety',
    'Failure Handling',
)

REQUIRED_TABLE_HEADERS = (
    ('Metric', 'Target'),
    ('Surface', 'Location', 'Purpose'),
    ('Action', 'Command'),
    ('Doc', 'Knowledge class', 'Purpose'),
)

PLACEHOLDER_PATTERNS = (
    r'\b(?:TODO|TBD|FIXME)\b',
    r'\bYYYY-MM-DD\b',
    r'\[PROJECT_NAME\]',
    r'<(?:fill|replace|preencher|project(?: name)?|todo|owner|date)[^>]*>',
    r'AGENTS_AUTHOR',
)

MINIMUM_MANDATORY_RULES = 8

MANDATORY_RULE_ANCHORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('file verification', ('before editing', 'antes de editar')),
    ('scoped changes', ('keep scope', 'mantenha o escopo')),
    ('current versus planned state', ('current state', 'estado atual')),
    ('canonical navigation', ('canonical doc', 'documentação canônica')),
)

EXECUTION_POLICY_ANCHORS: dict[
    str, tuple[tuple[str, tuple[str, ...]], ...]
] = {
    'Precedence': (
        ('authority rank', ('rank:', 'precedência:')),
        ('system constraints', ('system constraint', 'restrições de sistema')),
        ('user request', ('user request', 'pedido do usuário')),
    ),
    'Secrets': (
        ('secret types', ('.env', 'api keys', 'chaves de api')),
        ('redaction response', ('redact', 'redija')),
    ),
    'Repo Alignment': (
        ('canonical sources', ('canonical contract', 'contratos canônicos')),
        (
            'public contract protection',
            ('public contract', 'contratos públicos'),
        ),
        ('source conflict stop', ('disagree', 'discordarem')),
    ),
    'Autonomy': (
        ('reversible changes', ('reversible', 'reversíveis')),
        (
            'version control recovery',
            ('version control', 'controle de versão'),
        ),
        ('stop and ask', ('stop and ask', 'pare e peça')),
    ),
    'Validation': (
        ('official validation', ('official validation', 'validação oficial')),
        ('failure disclosure', ('failing', 'falhando')),
    ),
    'Execution Safety': (
        ('affected scope', ('what will be affected', 'o que será afetado')),
        ('dry run', ('dry run',)),
        ('script inspection', ('inspect the command', 'inspecione o comando')),
    ),
    'Failure Handling': (
        ('security boundary', ('security lock', 'bloqueio de segurança')),
        ('no workaround', ('do not work around', 'não contorne')),
    ),
}


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


def _subheadings_between(
    headings: list[tuple[int, str]], parent: str
) -> list[str]:
    result: list[str] = []
    in_parent = False
    for level, name in headings:
        if level == 2:
            in_parent = name == parent
            continue
        if in_parent and level == 3:
            result.append(name)
    return result


def _section_text(lines: list[str], *, level: int, name: str) -> str:
    """Return visible text inside one heading, excluding the heading itself."""
    heading = f'{"#" * level} {name}'
    result: list[str] = []
    in_section = False

    for line in lines:
        if line == heading:
            in_section = True
            continue
        match = re.match(r'^(#{1,6})\s+', line)
        if in_section and match and len(match.group(1)) <= level:
            break
        if in_section:
            result.append(line)

    return '\n'.join(result).strip()


def _table_pattern(columns: tuple[str, ...]) -> re.Pattern[str]:
    cells = r'\s*\|\s*'.join(re.escape(column) for column in columns)
    return re.compile(rf'^\|\s*{cells}\s*\|\s*$', flags=re.MULTILINE)


def _check_heading_contract(headings: list[tuple[int, str]]) -> list[str]:
    errors: list[str] = []
    top_level = tuple(name for level, name in headings if level == 2)
    if top_level != EXPECTED_TOP_LEVEL:
        errors.append(
            'level-2 headings must match portable contract order: '
            f'expected={EXPECTED_TOP_LEVEL!r}, actual={top_level!r}'
        )

    execution = tuple(_subheadings_between(headings, 'Execution Policy'))
    if execution != EXPECTED_EXECUTION_SUBHEADINGS:
        errors.append(
            'Execution Policy subheadings must match portable contract order: '
            f'expected={EXPECTED_EXECUTION_SUBHEADINGS!r}, actual={execution!r}'
        )

    configuration = _subheadings_between(headings, 'Configuration & Runtime')
    if 'Commands' not in configuration:
        errors.append('Configuration & Runtime must contain ### Commands')

    return errors


def _check_tables(text: str) -> list[str]:
    return [
        f'missing required table header: {" | ".join(columns)}'
        for columns in REQUIRED_TABLE_HEADERS
        if not _table_pattern(columns).search(text)
    ]


def _check_placeholders(text: str) -> list[str]:
    return [
        f'unresolved authoring marker found: {pattern}'
        for pattern in PLACEHOLDER_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def _contains_any(text: str, alternatives: tuple[str, ...]) -> bool:
    normalized = ' '.join(text.casefold().split())
    return any(
        ' '.join(alternative.casefold().split()) in normalized
        for alternative in alternatives
    )


def _check_policy_contract(lines: list[str]) -> list[str]:
    errors: list[str] = []
    mandatory = _section_text(lines, level=2, name='Mandatory Rules')
    rule_count = sum(
        1 for line in mandatory.splitlines() if re.match(r'^\s*-\s+\S', line)
    )
    if rule_count < MINIMUM_MANDATORY_RULES:
        errors.append(
            'Mandatory Rules must contain at least '
            f'{MINIMUM_MANDATORY_RULES} concrete bullet rules; found {rule_count}'
        )

    for label, alternatives in MANDATORY_RULE_ANCHORS:
        if not _contains_any(mandatory, alternatives):
            errors.append(f'Mandatory Rules missing policy anchor: {label}')

    for section, anchors in EXECUTION_POLICY_ANCHORS.items():
        content = _section_text(lines, level=3, name=section)
        if not content:
            errors.append(f'Execution Policy section is empty: {section}')
            continue
        for label, alternatives in anchors:
            if not _contains_any(content, alternatives):
                errors.append(
                    f'Execution Policy/{section} missing control: {label}'
                )

    return errors


def validate(text: str) -> list[str]:
    """Return contract violations in O(number of lines)."""
    lines = _visible_lines(text)
    visible_text = '\n'.join(lines)
    headings = _headings(lines)

    errors: list[str] = []
    errors.extend(_check_heading_contract(headings))
    errors.extend(_check_tables(visible_text))
    errors.extend(_check_placeholders(visible_text))
    errors.extend(_check_policy_contract(lines))
    return errors


def _payload(
    path: Path, errors: list[str], *, strict_governance: bool
) -> dict[str, Any]:
    return {
        'schema_version': 'agents-md-policy.v2',
        'status': 'passed' if not errors else 'failed',
        'file': str(path),
        'strict_governance': strict_governance,
        'errors': errors,
    }


def _render_text(payload: dict[str, Any]) -> str:
    status = str(payload['status']).upper()
    lines = [f'{status}: {payload["file"]}']
    lines.extend(f'- {error}' for error in payload['errors'])
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate AGENTS.md structure and operating policy contract.'
    )
    parser.add_argument(
        '--file',
        type=Path,
        default=Path('AGENTS.md'),
        help='AGENTS.md path to validate (default: AGENTS.md)',
    )
    parser.add_argument(
        '--strict-governance',
        action='store_true',
        help='Reject explicit draft fallbacks such as Unassigned or Draft.',
    )
    parser.add_argument(
        '--format',
        choices=('text', 'json'),
        default='text',
        help='Output format (default: text)',
    )
    args = parser.parse_args()

    try:
        text = args.file.read_text(encoding='utf-8')
    except OSError as exc:
        payload = {
            'schema_version': 'agents-md-policy.v2',
            'status': 'error',
            'file': str(args.file),
            'strict_governance': args.strict_governance,
            'errors': [str(exc)],
        }
        if args.format == 'json':
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(_render_text(payload), file=sys.stderr)
        return 2

    errors = validate(text)
    payload = _payload(
        args.file, errors, strict_governance=args.strict_governance
    )
    if args.format == 'json':
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(_render_text(payload))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
