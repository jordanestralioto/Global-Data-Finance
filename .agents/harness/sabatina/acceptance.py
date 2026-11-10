"""Validate aggregate completion criteria for work units."""

from __future__ import annotations

import re

from harness.sabatina.document import (
    Finding,
    Unit,
)
from harness.sabatina.markdown import (
    is_placeholder,
    normalize,
)

FIELD_LINE_RE = re.compile(r'^\s*-\s+\*\*([^*]+)\*\*\s*:\s*(.*?)\s*$')


AGGREGATE_FIELD_KEYS = frozenset({'aceite agregado', 'aggregate completion'})


AGGREGATE_ALL_MARKERS: tuple[str, ...] = (
    'todas as change',
    'todas as unidade',
    'cada change',
    'cada unidade',
    'unica change',
    'unica unidade',
    'every change',
    'every unit',
)


AGGREGATE_NEGATIONS: tuple[str, ...] = (
    'nenhum',
    'nenhuma',
    'sem passar',
    'no unit',
)


NUMBER_WORDS: dict[str, int] = {
    'uma': 1,
    'um': 1,
    'duas': 2,
    'dois': 2,
    'tres': 3,
    'quatro': 4,
    'cinco': 5,
    'seis': 6,
    'sete': 7,
    'oito': 8,
    'nove': 9,
    'dez': 10,
}


AGGREGATE_COUNT_RE = re.compile(
    r'\b(\d+|' + '|'.join(NUMBER_WORDS) + r')\s+(?:change|unidade|unit)',
)


AGGREGATE_ACCEPTANCE_RE = re.compile(
    r'^(?:'
    r'as?\s+(?:\d+|uma|um|duas|dois|tres|quatro|cinco|seis|sete|oito|'
    r'nove|dez)\s+(?:changes?|unidades?|units?)|'
    r'todas as\s+(?:changes?|unidades?)|'
    r'cada\s+(?:change|unidade|unit)|'
    r'a unica\s+(?:change|unidade)|'
    r'every\s+(?:change|unit)|'
    r'the only\s+(?:change|unit)'
    r')\s+(?:'
    r'passa|passam|passou|passaram'
    r')\s+(?:seu|seus|o|os)\s+(?:aceite|aceites|gate|gates)\b'
    r'(?:\s*(?:,|\.|$)|\s+e\b)'
)


def check_aggregate(
    units: list[Unit], body: list[tuple[int, str]]
) -> list[Finding]:
    if not units:
        return []
    value = ''
    for _, content in body:
        match = FIELD_LINE_RE.match(content)
        if match and normalize(match.group(1)) in AGGREGATE_FIELD_KEYS:
            value = match.group(2).strip()
            break
    if not value or is_placeholder(value):
        if len(units) < 2:
            return []
        return [
            Finding(
                'decomposition-aggregate-missing',
                'decomposicao com varias changes sem campo aceite agregado',
                line=units[0].line,
            )
        ]
    return _check_aggregate_value(value, units)


def _check_aggregate_value(value: str, units: list[Unit]) -> list[Finding]:
    """Require aggregate acceptance to cover every work unit."""
    normalized = normalize(value)
    declared = _declared_unit_count(normalized)
    if declared is not None and declared != len(units):
        return [
            Finding(
                'decomposition-aggregate-inconsistent',
                f'aceite agregado fala em {declared} unidades,'
                f' mas a tabela tem {len(units)}',
                line=units[0].line,
            )
        ]
    if _covers_every_unit(normalized, units) and _states_acceptance(
        normalized
    ):
        return []
    return [
        Finding(
            'decomposition-aggregate-unverifiable',
            'aceite agregado nao liga todas as changes a um criterio de'
            ' aceite',
            line=units[0].line,
        )
    ]


def _declared_unit_count(normalized: str) -> int | None:
    for match in AGGREGATE_COUNT_RE.finditer(normalized):
        word = match.group(1)
        if word.isdigit():
            return int(word)
        return NUMBER_WORDS[word]
    return None


def _covers_every_unit(normalized: str, units: list[Unit]) -> bool:
    if any(marker in normalized for marker in AGGREGATE_NEGATIONS):
        return False
    names = [normalize(unit.name) for unit in units]
    if all(name and name in normalized for name in names):
        return True
    if _declared_unit_count(normalized) == len(units):
        return True
    return any(marker in normalized for marker in AGGREGATE_ALL_MARKERS)


def _states_acceptance(normalized: str) -> bool:
    return '?' not in normalized and bool(
        AGGREGATE_ACCEPTANCE_RE.match(normalized)
    )
