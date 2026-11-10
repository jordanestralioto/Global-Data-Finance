"""Conservative signals about observed definitions, never runtime guarantees."""

from __future__ import annotations

import re

from .model import Column, Entity, Finding, Interpretation, Name

MONEY_WORDS = {'price', 'amount', 'total', 'subtotal', 'balance', 'cost'}
TEMPORAL_WORDS = {'at', 'date', 'time', 'timestamp'}
OPERATIONS = {
    'drop-data': ('high', 'Destructive table/data operation'),
    'drop-column': ('high', 'Column removal requires a compatibility window'),
    'drop-index': (
        'medium',
        'Index removal needs query and constraint evidence',
    ),
    'drop-constraint': (
        'medium',
        'Constraint removal changes integrity guarantees',
    ),
    'rename': (
        'medium',
        'Rename requires compatibility with deployed callers',
    ),
    'set-not-null': (
        'medium',
        'NOT NULL requires existing-data and lock evidence',
    ),
    'add-required-column': (
        'medium',
        'Required column needs rollout/backfill evidence',
    ),
    'change-type': (
        'medium',
        'Type change needs conversion and operational evidence',
    ),
}


def name_words(name: str) -> list[str]:
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return [word.lower() for word in re.split(r'[^\w]+|_', name) if word]


def type_findings(column: Column) -> list[Finding]:
    words = name_words(column.name)
    types = set(name_words(column.type_name))
    textual = bool(
        types & {'string', 'text', 'varchar', 'char', 'character', 'nvarchar'}
    )
    floating = bool(types & {'float', 'real', 'double', 'float4', 'float8'})
    if not words or column.type_name.endswith('[]'):
        return []
    risks: list[str] = []
    if set(words) & MONEY_WORDS and (textual or floating):
        risks.append(
            'Arithmetic-looking field uses text or floating point; confirm semantics'
        )
    boolean = words[0] in {'is', 'has'} or words[-1] in {
        'enabled',
        'active',
        'disabled',
        'archived',
        'verified',
        'deleted',
    }
    if boolean and textual:
        risks.append('Boolean-looking field uses text; confirm the domain')
    if words[-1] in TEMPORAL_WORDS and textual:
        risks.append(
            'Temporal-looking field uses text; confirm the stored representation'
        )
    return [
        Finding(
            'schema/data-type',
            'medium',
            risk,
            column.line,
            f'{column.name}: {column.type_name}',
            'Verify domain semantics and native types; names alone do not prove an error.',
        )
        for risk in risks
    ]


def supports(index: tuple[str, ...], foreign_key: tuple[str, ...]) -> bool:
    return len(index) >= len(foreign_key) and set(
        index[: len(foreign_key)]
    ) == set(foreign_key)


def entity_findings(
    entity: Entity,
    declared_indexes: list[tuple[str, ...]],
    primary_key: tuple[str, ...],
) -> list[Finding]:
    result: list[Finding] = []
    label = '.'.join(entity.name)
    if entity.definition and not primary_key:
        result.append(
            Finding(
                'schema/primary-key',
                'medium',
                f'{label}: no explicit primary key observed',
                entity.line,
                label,
                'Check the native schema and lifecycle; document an intentional keyless table.',
            )
        )
    for column in entity.columns:
        result.extend(type_findings(column))
    result.extend(
        Finding(
            'schema/foreign-key-index',
            'medium',
            f'{label}: no declared index beginning with FK columns observed',
            entity.line,
            ', '.join(key),
            'Check existing indexes and query plans before adding an index; FK indexes are workload-dependent.',
        )
        for key in entity.foreign_keys
        if not any(supports(index, key) for index in declared_indexes)
    )
    return result


def index_catalog(
    interpretations: list[Interpretation],
) -> dict[Name, list[tuple[str, ...]]]:
    catalog: dict[Name, list[tuple[str, ...]]] = {}
    for interpretation in interpretations:
        for entity in interpretation.entities:
            catalog.setdefault(entity.name, []).extend(entity.indexes)
        for index in interpretation.indexes:
            if not index.partial and index.method in {'btree', 'hash'}:
                catalog.setdefault(index.table, []).append(index.columns)
    return catalog


def evaluate(
    interpretation: Interpretation,
    catalog: dict[Name, list[tuple[str, ...]]],
    primary_keys: dict[Name, tuple[str, ...]],
) -> list[Finding]:
    result: list[Finding] = []
    for entity in interpretation.entities:
        result.extend(
            entity_findings(
                entity,
                catalog.get(entity.name, []),
                primary_keys.get(entity.name, ()),
            )
        )
    for operation in interpretation.operations:
        if operation.kind in OPERATIONS:
            severity, summary = OPERATIONS[operation.kind]
            result.append(
                Finding(
                    'migration/rollout',
                    severity,
                    summary,
                    operation.line,
                    operation.kind,
                    'Review expand/contract, deployed callers, lock budget and recovery before execution.',
                )
            )
    return result
