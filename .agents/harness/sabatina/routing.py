"""Classify and validate the declared follow-up route."""

from __future__ import annotations

from dataclasses import dataclass

from harness.sabatina.document import (
    Document,
    Finding,
    subsection_body,
)
from harness.sabatina.markdown import (
    find_table,
    normalize,
    parse_tables,
)

HANDOFF_ROUTE_SECTION = 'proximo workflow proposto'


ROUTE_DIRECT = 'execucao direta'


ROUTE_PLAN = 'plano'


ROUTE_OPENSPEC = 'openspec'


ROUTES = (ROUTE_DIRECT, ROUTE_PLAN, ROUTE_OPENSPEC)


ROUTE_MARKERS: dict[str, tuple[str, ...]] = {
    ROUTE_OPENSPEC: ('openspec',),
    ROUTE_PLAN: ('plano',),
    ROUTE_DIRECT: ('execucao direta',),
}


AUTHORIZATION_MARKERS: tuple[str, ...] = ('autoriza', 'autorizacao')


ROUTE_CRITERIA: tuple[str, ...] = (
    'contrato duradouro',
    'multiplos consumidores',
    'dado persistido novo',
    'rollout supervisionado',
    'rollback proprio',
    'lifecycle auditavel',
    'varios passos',
)


OPENSPEC_CRITERIA: tuple[str, ...] = tuple(
    criterion
    for criterion in ROUTE_CRITERIA[:-1]
    if criterion != 'dado persistido novo'
)


PLAN_CRITERION = ROUTE_CRITERIA[-1]


TRUE_ANSWERS = frozenset({'sim', 'yes', 'true'})


FALSE_ANSWERS = frozenset({'nao', 'no', 'false'})


ROUTE_RECOMMENDATION_KEY = 'rota recomendada'


ROUTE_AUTHORIZATION_KEY = 'autorizacao explicita'


ROUTE_ALIASES: dict[str, str] = {
    'execucao direta': ROUTE_DIRECT,
    'direta': ROUTE_DIRECT,
    'direct execution': ROUTE_DIRECT,
    'plano': ROUTE_PLAN,
    'plano md': ROUTE_PLAN,
    'bounded plan': ROUTE_PLAN,
    'openspec': ROUTE_OPENSPEC,
}


AUTHORIZATION_VALUES = frozenset(
    {
        'pendente',
        'aguardando',
        'nao iniciada',
        'autorizacao separada',
        'autorizada separadamente',
    }
)


@dataclass(frozen=True)
class RouteDecision:
    """A recommended route or the criteria still missing."""

    route: str | None
    unmet: tuple[str, ...]


def classify_route(answers: dict[str, bool | None]) -> RouteDecision:
    """Choose the smallest route preserving the declared contract.

    Missing criteria stay explicit; classification does not authorize execution.
    """
    unmet = tuple(name for name in ROUTE_CRITERIA if answers.get(name) is None)
    if unmet:
        return RouteDecision(route=None, unmet=unmet)
    if any(answers[name] for name in OPENSPEC_CRITERIA):
        return RouteDecision(route=ROUTE_OPENSPEC, unmet=())
    if answers[PLAN_CRITERION]:
        return RouteDecision(route=ROUTE_PLAN, unmet=())
    return RouteDecision(route=ROUTE_DIRECT, unmet=())


def _declared_routes(text: str) -> set[str]:
    return {
        route
        for route, markers in ROUTE_MARKERS.items()
        if any(marker in text for marker in markers)
    }


def route_value(table: list[tuple[int, list[str]]], key: str) -> str:
    wanted = normalize(key)
    for _, cells in table[1:]:
        if cells and normalize(cells[0]) == wanted and len(cells) >= 2:
            return normalize(cells[1])
    return ''


def route_from_value(value: str) -> str | None:
    normalized = normalize(value)
    return ROUTE_ALIASES.get(normalized)


def _route_matrix_keys(
    table: list[tuple[int, list[str]]],
) -> tuple[set[str], dict[str, int]]:
    declared: set[str] = set()
    counts: dict[str, int] = {}
    for _, cells in table[1:]:
        if not cells:
            continue
        key = normalize(cells[0])
        declared.add(key)
        counts[key] = counts.get(key, 0) + 1
    return declared, counts


def _route_answers(
    table: list[tuple[int, list[str]]],
) -> dict[str, bool | None]:
    answers: dict[str, bool | None] = {}
    for _, cells in table[1:]:
        if len(cells) < 2:
            continue
        value = normalize(cells[1])
        if value in TRUE_ANSWERS:
            answers[normalize(cells[0])] = True
        elif value in FALSE_ANSWERS:
            answers[normalize(cells[0])] = False
        else:
            answers[normalize(cells[0])] = None
    return answers


def _check_route_declaration(text: str, line: int) -> list[Finding]:
    findings: list[Finding] = []
    if not _declared_routes(text):
        findings.append(
            Finding(
                'route-missing',
                'proximo workflow sem nenhuma das tres rotas',
                line=line,
            )
        )
    if not any(marker in text for marker in AUTHORIZATION_MARKERS):
        findings.append(
            Finding(
                'route-authorization-missing',
                'proximo workflow sem exigir autorizacao explicita',
                line=line,
            )
        )
    return findings


def _check_route_criteria(table: list[tuple[int, list[str]]]) -> list[Finding]:
    line = table[0][0]
    declared, counts = _route_matrix_keys(table)
    required = set(ROUTE_CRITERIA)
    findings = [
        Finding(
            'route-criterion-missing',
            'matriz de rota sem o criterio ' + repr(criterion),
            line=line,
        )
        for criterion in ROUTE_CRITERIA
        if criterion not in declared
    ]
    findings.extend(
        Finding(
            'route-criterion-duplicate',
            'matriz de rota repete o criterio ' + repr(criterion),
            line=line,
        )
        for criterion, count in counts.items()
        if criterion in required and count > 1
    )
    if findings:
        return findings

    decision = classify_route(_route_answers(table))
    if decision.unmet:
        findings.append(
            Finding(
                'route-criteria-incomplete',
                'criterio de rota nao declarado: ' + ', '.join(decision.unmet),
                line=line,
            )
        )
        return findings

    declared_route = route_from_value(
        route_value(table, ROUTE_RECOMMENDATION_KEY)
    )
    if declared_route is None:
        findings.append(
            Finding(
                'route-recommendation-missing',
                'matriz de rota sem uma rota recomendada valida',
                line=line,
            )
        )
    elif declared_route != decision.route:
        findings.append(
            Finding(
                'route-mismatch',
                f'criterios levam a {decision.route!r},'
                f' mas a matriz recomenda {declared_route!r}',
                line=line,
            )
        )
    authorization = route_value(table, ROUTE_AUTHORIZATION_KEY)
    if authorization not in AUTHORIZATION_VALUES:
        findings.append(
            Finding(
                'route-authorization-missing',
                'matriz de rota deve registrar autorizacao separada como'
                ' pendente ou concedida separadamente',
                line=line,
            )
        )
    return findings


def check_route(document: Document) -> list[Finding]:
    """Validate a reproducible recommendation with separate authorization."""
    body = subsection_body(document, 'handoff', HANDOFF_ROUTE_SECTION)
    if not body:
        return []
    text = normalize('\n'.join(content for _, content in body))
    findings = _check_route_declaration(text, body[0][0])
    criteria = find_table(parse_tables(body), 'criterio')
    if criteria is None:
        findings.append(
            Finding(
                'route-criteria-missing',
                'proximo workflow sem a matriz deterministica de criterios',
                line=body[0][0],
            )
        )
    else:
        findings.extend(_check_route_criteria(criteria))
    return findings
