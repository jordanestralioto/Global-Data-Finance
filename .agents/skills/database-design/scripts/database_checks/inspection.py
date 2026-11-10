"""Inspect selected artifacts and keep unverified coverage visible."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import prisma, rules, sql
from .discovery import discover
from .model import FileReview, Interpretation, Name

LIMITATIONS = [
    'Heuristic triage, not native SQL/ORM validation or a database safety verdict.',
    'Declarations do not reconstruct the applied migration history or live catalog.',
    'Ownership, authorization, concurrency, query performance and lock behavior require contextual/native evidence.',
    'Indexes are matched by explicit names; search paths and implicit engine indexes are not inferred.',
]


def display_path(path: Path) -> str:
    return Path(os.path.relpath(path, Path.cwd())).as_posix()


def inspect_file(
    path: Path, max_bytes: int
) -> tuple[FileReview, Interpretation]:
    format_name = path.suffix.lower().lstrip('.') or 'unknown'
    review = FileReview(display_path(path), format_name)
    interpretation = Interpretation()
    if format_name not in {'sql', 'prisma'}:
        review.unverified.append(
            'Source artifact inventoried only; inspect its generated SQL or run the repository-native schema tooling.'
        )
        return review, interpretation
    try:
        if path.stat().st_size > max_bytes:
            review.unverified.append(
                f'File exceeds the declared {max_bytes}-byte inspection limit.'
            )
            return review, interpretation
        content = path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        review.coverage = 'error'
        review.errors.append(f'Cannot read UTF-8 input: {exc}')
        return review, interpretation
    interpretation = (
        sql.interpret(content)
        if format_name == 'sql'
        else prisma.interpret(content)
    )
    review.units_checked = interpretation.units_checked
    review.statements_seen = interpretation.statements_seen
    review.statements_checked = interpretation.statements_checked
    review.unverified.extend(interpretation.unverified)
    if review.units_checked:
        review.coverage = 'partial' if review.unverified else 'complete'
    else:
        review.unverified.append(
            'No supported table, model, index or migration operation was interpreted.'
        )
    return review, interpretation


def primary_keys(
    interpretations: list[Interpretation],
) -> dict[Name, tuple[str, ...]]:
    return {
        entity.name: entity.primary_key
        for interpretation in interpretations
        for entity in interpretation.entities
        if entity.primary_key
    }


def evaluate_files(pairs: list[tuple[FileReview, Interpretation]]) -> None:
    sql_inputs = [parsed for review, parsed in pairs if review.format == 'sql']
    definitions = Counter(
        entity.name
        for parsed in sql_inputs
        for entity in parsed.entities
        if entity.definition
    )
    ambiguous = {name for name, count in definitions.items() if count > 1}
    sql_catalog = rules.index_catalog(sql_inputs)
    sql_primary_keys = primary_keys(sql_inputs)
    for review, parsed in pairs:
        catalog, keys = sql_catalog, sql_primary_keys
        if review.format != 'sql':
            catalog, keys = (
                rules.index_catalog([parsed]),
                primary_keys([parsed]),
            )
        if review.format == 'sql' and any(
            entity.name in ambiguous for entity in parsed.entities
        ):
            catalog, keys = (
                rules.index_catalog([parsed]),
                primary_keys([parsed]),
            )
            review.coverage = 'partial'
            review.unverified.append(
                'Repeated table definitions: review database/migration boundaries separately; cross-file indexes were not inferred.'
            )
        review.findings = rules.evaluate(parsed, catalog, keys)


def inspect_paths(
    paths: list[Path],
    *,
    includes: list[str],
    excludes: list[str],
    max_files: int,
    max_bytes: int,
) -> tuple[dict[str, Any], int]:
    discovery = discover(paths, includes, excludes)
    selected = discovery.files[:max_files]
    pairs = [inspect_file(path, max_bytes) for path in selected]
    evaluate_files(pairs)
    reviews = [review for review, _ in pairs]
    severities = Counter(
        finding.severity for review in reviews for finding in review.findings
    )
    errors = discovery.errors + [
        error for review in reviews for error in review.errors
    ]
    omitted = len(discovery.files) - len(selected)
    incomplete = (
        not reviews
        or omitted > 0
        or any(review.coverage != 'complete' for review in reviews)
    )
    if errors:
        status, exit_code = 'inspection-error', 2
    elif incomplete:
        status, exit_code = 'incomplete', 3
    elif severities['high']:
        status, exit_code = 'findings', 1
    else:
        status, exit_code = 'complete', 0
    report = {
        'schema_version': 1,
        'script': 'check_schema',
        'status': status,
        'passed': exit_code == 0,
        'files_found': len(discovery.files),
        'files_inspected': len(reviews),
        'files_omitted': omitted,
        'units_checked': sum(review.units_checked for review in reviews),
        'coverage': dict(Counter(review.coverage for review in reviews)),
        'findings_by_severity': dict(severities),
        'errors': errors,
        'files': [asdict(review) for review in reviews],
        'limitations': LIMITATIONS,
    }
    return report, exit_code
