#!/usr/bin/env python3
"""Normaliza frontmatter de skills removendo metadados fora do contrato mínimo."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = HARNESS_ROOT / 'skills'
ALLOWED_ACTIVE_KEYS = {'name', 'description'}
ALLOWED_ARCHIVED_KEYS = {'name', 'description', 'status', 'replaced_by'}
SKIP_PARTS = {
    '__pycache__',
    'references',
    'assets',
    'scripts',
    'templates',
    'schemas',
    'data',
}


def parse_frontmatter(text: str) -> tuple[str, str, str]:
    match = re.match(
        r'(?P<start>---\n)(?P<fm>.*?)(?P<end>\n---\n)(?P<body>.*)\Z',
        text,
        re.S,
    )
    if not match:
        return ('', '', text)
    return match.group('start'), match.group('fm'), match.group('body')


def parse_metadata_keys(frontmatter: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if not line.strip() or line.startswith((' ', '\t')) or ':' not in line:
            continue
        key, raw_value = line.split(':', 1)
        keys[key.strip()] = raw_value.strip()
    return keys


def normalize_frontmatter(frontmatter: str) -> tuple[str, list[str]]:
    metadata = parse_metadata_keys(frontmatter)
    allowed_keys = (
        ALLOWED_ARCHIVED_KEYS
        if metadata.get('status', '').strip().strip('"\'') == 'archived'
        else ALLOWED_ACTIVE_KEYS
    )

    removed: list[str] = []
    normalized_lines: list[str] = []
    skipping_multiline = False

    for line in frontmatter.splitlines():
        if skipping_multiline:
            if line.startswith((' ', '\t')):
                continue
            skipping_multiline = False

        if not line.strip():
            normalized_lines.append(line)
            continue

        if line.startswith((' ', '\t')):
            normalized_lines.append(line)
            continue

        if ':' not in line:
            normalized_lines.append(line)
            continue

        key, raw_value = line.split(':', 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if key not in allowed_keys:
            removed.append(key)
            if raw_value in {'>', '|', '>-', '|-'}:
                skipping_multiline = True
            continue

        normalized_lines.append(line)

    return '\n'.join(normalized_lines).rstrip('\n') + '\n', removed


def iter_skill_files() -> list[Path]:
    files: list[Path] = []
    for path in SKILLS_ROOT.rglob('SKILL.md'):
        rel_parts = path.relative_to(SKILLS_ROOT).parts
        if any(part in SKIP_PARTS for part in rel_parts):
            continue
        files.append(path)
    return sorted(files)


def normalize_skill(path: Path, check_only: bool) -> tuple[bool, list[str]]:
    text = path.read_text(encoding='utf-8')
    start, frontmatter, body = parse_frontmatter(text)
    if not frontmatter:
        return (False, [])

    normalized_frontmatter, removed = normalize_frontmatter(frontmatter)
    if not removed:
        return (False, [])

    if not check_only:
        path.write_text(
            f'{start}{normalized_frontmatter}---\n{body}', encoding='utf-8'
        )
    return (True, removed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Remove metadados extras do frontmatter de skills para seguir skill-governance.'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Falha se alguma skill ainda tiver metadados extras.',
    )
    args = parser.parse_args()

    changed: list[str] = []
    for path in iter_skill_files():
        modified, removed = normalize_skill(path, check_only=args.check)
        if modified:
            changed.append(
                f'{path.relative_to(HARNESS_ROOT)}: removed {sorted(set(removed))}'
            )

    if changed:
        print('\n'.join(changed))
        return 1 if args.check else 0

    print(
        'All skills already follow the minimal skill-governance frontmatter contract.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
