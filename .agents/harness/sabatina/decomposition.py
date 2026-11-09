"""Read and validate ownership of handoff work units."""

from __future__ import annotations

from harness.sabatina.acceptance import (
    check_aggregate,
)
from harness.sabatina.document import (
    QID_RE,
    Document,
    Finding,
    Unit,
    subsection_body,
)
from harness.sabatina.markdown import (
    DASHES,
    find_table,
    is_empty,
    is_placeholder,
    normalize,
    parse_tables,
)
from harness.sabatina.questions import (
    dependency_cycle,
)
from harness.sabatina.routing import (
    HANDOFF_ROUTE_SECTION,
    ROUTE_OPENSPEC,
    ROUTE_RECOMMENDATION_KEY,
    route_from_value,
    route_value,
)

NO_DEPENDENCY = frozenset(
    {'nenhuma', 'nenhum', 'none', '-', *DASHES, 'n/a', ''}
)


UNIT_COLUMN_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('name', ('change', 'work unit', 'unidade')),
    ('owned', ('ids',)),
    ('objective', ('objetivo', 'objective')),
    ('acceptance', ('aceite', 'acceptance')),
    ('rollout', ('rollout',)),
    ('rollback', ('rollback',)),
    ('dependencies', ('depende', 'depends')),
)


def _strip_code(value: str) -> str:
    return value.replace('`', '').strip()


def _dependency_names(raw: str) -> list[str]:
    cleaned = _strip_code(raw)
    if normalize(cleaned) in NO_DEPENDENCY:
        return []
    return [
        _strip_code(part)
        for part in cleaned.split(',')
        if normalize(_strip_code(part)) not in NO_DEPENDENCY
    ]


def _unit_column_indices(header: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for key, markers in UNIT_COLUMN_MARKERS:
        for index, cell in enumerate(header):
            normalized = normalize(cell)
            if any(marker in normalized for marker in markers):
                indices[key] = index
                break
    return indices


def _decomposition_units(table: list[tuple[int, list[str]]]) -> list[Unit]:
    _, header = table[0]
    indices = _unit_column_indices(header)
    units: list[Unit] = []
    for number, cells in table[1:]:
        owned = (
            QID_RE.findall(cells[indices['owned']])
            if 'owned' in indices and indices['owned'] < len(cells)
            else []
        )
        values = {
            key: cells[index] if index < len(cells) else ''
            for key, index in indices.items()
        }
        raw_deps = values.get('dependencies', '')
        units.append(
            Unit(
                name=_strip_code(
                    values.get('name', cells[0] if cells else '')
                ),
                line=number,
                owned=tuple(owned),
                objective=values.get('objective', ''),
                acceptance=values.get('acceptance', ''),
                rollout=values.get('rollout', ''),
                rollback=values.get('rollback', ''),
                dependencies=tuple(_dependency_names(raw_deps)),
                cells=tuple(cells),
            )
        )
    return units


def decision_units(document: Document) -> list[Unit]:
    """Read the declared work units without exposing Markdown internals."""
    body = subsection_body(document, 'handoff', HANDOFF_ROUTE_SECTION)
    table = find_table(parse_tables(body), 'ids')
    return _decomposition_units(table) if table else []


def _check_unit_cells(unit: Unit) -> list[Finding]:
    incomplete = any(
        is_empty(cell) or is_placeholder(cell) for cell in unit.cells
    )
    if not incomplete:
        return []
    return [
        Finding(
            'decomposition-row-incomplete',
            f'{unit.name} com coluna vazia ou de template',
            line=unit.line,
        )
    ]


def _check_unit_rows(units: list[Unit], known: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    names: set[str] = set()
    for unit in units:
        findings.extend(_check_unit_cells(unit))
        if not unit.name:
            findings.append(
                Finding(
                    'decomposition-name-missing',
                    'unidade de decomposicao sem nome',
                    line=unit.line,
                )
            )
        elif unit.name in names:
            findings.append(
                Finding(
                    'decomposition-name-duplicate',
                    f'unidade de decomposicao repetida: {unit.name}',
                    line=unit.line,
                )
            )
        names.add(unit.name)
        if not unit.owned:
            findings.append(
                Finding(
                    'decomposition-umbrella',
                    f'{unit.name} nao possui nenhuma decisao',
                    line=unit.line,
                )
            )
        findings.extend(
            Finding(
                'decomposition-id-unknown',
                f'{unit.name} possui {qid}, que nao existe',
                line=unit.line,
            )
            for qid in unit.owned
            if qid not in known
        )
        for field_name, value in (
            ('objetivo', unit.objective),
            ('aceite', unit.acceptance),
            ('rollout', unit.rollout),
            ('rollback', unit.rollback),
        ):
            if is_empty(value) or is_placeholder(value):
                findings.append(
                    Finding(
                        'decomposition-field-missing',
                        f'{unit.name} sem {field_name} verificavel',
                        line=unit.line,
                    )
                )
    return findings


def _check_unit_ownership(units: list[Unit]) -> list[Finding]:
    owners: dict[str, list[str]] = {}
    for unit in units:
        for qid in unit.owned:
            owners.setdefault(qid, []).append(unit.name)
    return [
        Finding(
            'decomposition-duplicate-owner',
            f'{qid} pertence a mais de uma change: ' + ', '.join(names),
        )
        for qid, names in owners.items()
        if len(names) > 1
    ]


def _check_unit_coverage(units: list[Unit], known: set[str]) -> list[Finding]:
    owned = {qid for unit in units for qid in unit.owned}
    return [
        Finding(
            'decomposition-owner-missing',
            f'{qid} nao pertence a nenhuma change',
        )
        for qid in sorted(known - owned, key=lambda item: int(item[1:]))
    ]


def _check_unit_graph(units: list[Unit]) -> list[Finding]:
    names = {unit.name for unit in units}
    findings: list[Finding] = []
    for unit in units:
        for target in unit.dependencies:
            if target == unit.name:
                findings.append(
                    Finding(
                        'decomposition-dependency-self',
                        f'{unit.name} depende de si mesma',
                        line=unit.line,
                    )
                )
            elif target not in names:
                findings.append(
                    Finding(
                        'decomposition-dependency-unknown',
                        f'{unit.name} depende de {target},'
                        ' que nao esta na tabela',
                        line=unit.line,
                    )
                )
    cycle = dependency_cycle(
        {unit.name: list(unit.dependencies) for unit in units}
    )
    if cycle is not None:
        findings.append(
            Finding(
                'decomposition-cycle',
                'ciclo entre changes: ' + ' -> '.join(cycle),
            )
        )
    return findings


def check_decomposition(document: Document) -> list[Finding]:
    """Validate exclusive ownership and dependencies for zero or more units."""
    body = subsection_body(document, 'handoff', HANDOFF_ROUTE_SECTION)
    if not body:
        return []
    route_table = find_table(parse_tables(body), 'criterio')
    declared_route = (
        route_from_value(route_value(route_table, ROUTE_RECOMMENDATION_KEY))
        if route_table is not None
        else None
    )
    table = find_table(parse_tables(body), 'ids')
    if table is None:
        if declared_route != ROUTE_OPENSPEC:
            return []
        return [
            Finding(
                'decomposition-missing',
                'rota OpenSpec exige decomposicao formal das decisoes',
                line=body[0][0],
            )
        ]
    indices = _unit_column_indices(table[0][1])
    missing_columns = [
        key for key, _ in UNIT_COLUMN_MARKERS if key not in indices
    ]
    if missing_columns:
        return [
            Finding(
                'decomposition-columns-missing',
                'tabela de decomposicao sem colunas: '
                + ', '.join(missing_columns),
                line=table[0][0],
            )
        ]
    units = _decomposition_units(table)
    known = {question.qid for question in document.questions}
    findings = _check_unit_rows(units, known)
    findings.extend(_check_unit_ownership(units))
    if declared_route == ROUTE_OPENSPEC:
        findings.extend(_check_unit_coverage(units, known))
    findings.extend(_check_unit_graph(units))
    findings.extend(check_aggregate(units, body))
    return findings
