"""Purpose operations and prefix sections for deterministic spec sync."""

from __future__ import annotations

import re

PURPOSE_RE = re.compile(r'^##\s+Purpose\s*$', re.I)
MODIFIED_PURPOSE_RE = re.compile(r'^##\s+MODIFIED\s+Purpose\s*$', re.I)
REQUIREMENTS_RE = re.compile(r'^##\s+Requirements\s*$', re.I)
PLACEHOLDER_RE = re.compile(r'\b(?:TBD|TODO|FIXME|XXX)\b|<[^>]+>', re.I)
DECISION_SOURCE_RE = re.compile(
    r'^[ \t]*Decision source:[ \t]*(.+?)[ \t]*$', re.MULTILINE
)


def normalize_block(lines: list[str]) -> str:
    cleaned = [line.rstrip() for line in lines]
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return '\n'.join(cleaned)


def section_body(lines: list[str], heading: re.Pattern[str]) -> str:
    start = next(
        (index + 1 for index, line in enumerate(lines) if heading.match(line)),
        None,
    )
    if start is None:
        return ''
    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith('## ')
        ),
        len(lines),
    )
    return normalize_block(lines[start:end]).strip()


def parse_purpose_operation(text: str) -> str | None:
    lines = text.splitlines()
    headings = [line for line in lines if MODIFIED_PURPOSE_RE.match(line)]
    if not headings:
        return None
    if len(headings) != 1:
        raise ValueError(
            'delta must contain at most one MODIFIED Purpose operation'
        )
    replacement = section_body(lines, MODIFIED_PURPOSE_RE)
    if not replacement or PLACEHOLDER_RE.search(replacement):
        raise ValueError('MODIFIED Purpose requires a concrete nonempty body')
    if DECISION_SOURCE_RE.search(replacement):
        raise ValueError('MODIFIED Purpose cannot replace decision provenance')
    ordinary_count = sum(1 for line in lines if PURPOSE_RE.match(line))
    if ordinary_count > 1:
        raise ValueError(
            'MODIFIED Purpose allows at most one delta Purpose section'
        )
    ordinary = section_body(lines, PURPOSE_RE)
    if ordinary_count and ordinary != replacement:
        raise ValueError('delta Purpose and MODIFIED Purpose disagree')
    return replacement


def replace_purpose(prefix: str, replacement: str) -> str:
    lines = prefix.splitlines()
    headings = [
        index for index, line in enumerate(lines) if PURPOSE_RE.match(line)
    ]
    if len(headings) != 1:
        raise ValueError(
            'MODIFIED Purpose requires exactly one canonical Purpose'
        )
    start = headings[0] + 1
    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith('## ')
            or DECISION_SOURCE_RE.match(lines[index])
        ),
        len(lines),
    )
    return '\n'.join([*lines[:start], '', replacement, '', *lines[end:]])


def with_provenance(prefix: str, decision_ids: tuple[str, ...]) -> str:
    lines = prefix.splitlines()
    heading = next(
        i for i, line in enumerate(lines) if REQUIREMENTS_RE.match(line)
    )
    prefix_text = '\n'.join(lines[:heading])
    existing_ids = DECISION_SOURCE_RE.findall(prefix_text)
    source_ids = set(re.findall(r'Q\d+', ','.join(existing_ids)))
    merged_ids = sorted(
        source_ids | set(decision_ids), key=lambda item: int(item[1:])
    )
    clean_prefix = (
        DECISION_SOURCE_RE.sub('', prefix_text).rstrip().splitlines()
    )
    provenance = [f'Decision source: {item}' for item in merged_ids]
    return normalize_block(
        [*clean_prefix, '', *provenance, '', *lines[heading:]]
    )
