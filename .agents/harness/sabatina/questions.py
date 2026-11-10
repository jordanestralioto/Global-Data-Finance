"""Validate question fields, dependency graphs and score arithmetic."""

from __future__ import annotations

import re

from harness.sabatina.document import (
    OPEN_STATES,
    QID_RE,
    SCORE_COLUMNS,
    TERMINAL_STATES,
    VALID_STATES,
    Document,
    Finding,
    Question,
    valid_date,
)
from harness.sabatina.markdown import (
    is_empty,
    is_terminal_placeholder,
    normalize,
)

TERMINAL_FIELDS: dict[str, str] = {
    'respondida': 'resposta',
    'apurada': 'evidencia',
    'assumida': 'premissa',
    'descartada': 'descartada-por',
}


def _state_requirements(question: Question) -> list[Finding]:
    state = question.state
    findings: list[Finding] = []
    if state == 'respondida' and not question.has_prefixed('resposta'):
        findings.append(
            Finding(
                'field-missing',
                'estado respondida exige o campo resposta',
                question=question.qid,
                line=question.line,
            )
        )
    elif state == 'respondida' and not valid_date(question.answered_on):
        findings.append(
            Finding(
                'answer-date-invalid',
                'estado respondida exige resposta datada em AAAA-MM-DD valido',
                question=question.qid,
                line=question.line,
            )
        )
    if state == 'apurada' and not question.has('evidencia'):
        findings.append(
            Finding(
                'field-missing',
                'estado apurada exige o campo evidencia',
                question=question.qid,
                line=question.line,
            )
        )
    if state == 'descartada' and not QID_RE.search(
        question.value('descartada-por')
    ):
        findings.append(
            Finding(
                'field-missing',
                'estado descartada exige descartada-por com um Qn',
                question=question.qid,
                line=question.line,
            )
        )
    if state == 'assumida':
        findings.extend(_premise_requirements(question))
    findings.extend(_placeholder_requirements(question))
    return findings


def _placeholder_requirements(question: Question) -> list[Finding]:
    name = TERMINAL_FIELDS.get(question.state)
    if name is None:
        return []
    value = question.prefixed_value(name)
    if not value or not is_terminal_placeholder(value):
        return []
    return [
        Finding(
            'field-placeholder',
            f'campo {name} ainda com texto de template',
            question=question.qid,
            line=question.line,
        )
    ]


def _premise_requirements(question: Question) -> list[Finding]:
    premise = normalize(question.value('premissa'))
    if not premise:
        return [
            Finding(
                'field-missing',
                'estado assumida exige o campo premissa',
                question=question.qid,
                line=question.line,
            )
        ]
    parts = re.split(r'(valida com:|reabre quando:)', premise)
    conditions = {
        marker: value.strip(' |')
        for marker, value in zip(parts[1::2], parts[2::2], strict=True)
    }
    missing = [
        marker
        for marker in ('valida com:', 'reabre quando:')
        if is_empty(conditions.get(marker, ''))
    ]
    if is_empty(parts[0].strip(' |')):
        missing.insert(0, 'texto da premissa')
    return [
        Finding(
            'premise-incomplete',
            f'premissa sem valor para {marker!r}',
            question=question.qid,
            line=question.line,
        )
        for marker in missing
    ]


def check_questions(document: Document) -> list[Finding]:
    findings: list[Finding] = []
    for question in document.questions:
        if question.state not in VALID_STATES:
            findings.append(
                Finding(
                    'state-invalid',
                    f'estado {question.state!r} fora de'
                    f' {sorted(VALID_STATES)}',
                    question=question.qid,
                    line=question.line,
                )
            )
            continue
        if not question.has('pergunta'):
            findings.append(
                Finding(
                    'field-missing',
                    'campo pergunta ausente ou vazio',
                    question=question.qid,
                    line=question.line,
                )
            )
        findings.extend(_state_requirements(question))
    return findings


def _dependency_edges(document: Document) -> dict[str, list[str]]:
    return {
        question.qid: question.dependencies for question in document.questions
    }


def dependency_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []

    def walk(node: str) -> list[str] | None:
        if node in done:
            return None
        if node in visiting:
            start = stack.index(node)
            return [*stack[start:], node]
        visiting.add(node)
        stack.append(node)
        for target in edges.get(node, []):
            if target not in edges:
                continue
            cycle = walk(target)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.discard(node)
        done.add(node)
        return None

    for node in edges:
        cycle = walk(node)
        if cycle is not None:
            return cycle
    return None


def check_graph(document: Document) -> list[Finding]:
    edges = _dependency_edges(document)
    states = {q.qid: q.state for q in document.questions}
    findings: list[Finding] = []
    for question in document.questions:
        findings.extend(_check_question_edges(question, edges, states))
    cycle = dependency_cycle(edges)
    if cycle is not None:
        findings.append(
            Finding(
                'dependency-cycle',
                'ciclo em bloqueada-por: ' + ' -> '.join(cycle),
            )
        )
    return findings


def _check_question_edges(
    question: Question,
    edges: dict[str, list[str]],
    states: dict[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    dependencies = question.dependencies
    for target in dependencies:
        if target == question.qid:
            findings.append(
                Finding(
                    'dependency-self',
                    'duvida depende de si mesma',
                    question=question.qid,
                    line=question.line,
                )
            )
        elif target not in edges:
            findings.append(
                Finding(
                    'dependency-unknown',
                    f'bloqueada-por aponta para {target}, que nao existe',
                    question=question.qid,
                    line=question.line,
                )
            )
    open_targets = [
        target
        for target in dependencies
        if states.get(target, '') in OPEN_STATES
    ]
    findings.extend(
        _check_edge_coherence(question, open_targets, dependencies)
    )
    return findings


def _check_edge_coherence(
    question: Question,
    open_targets: list[str],
    dependencies: list[str],
) -> list[Finding]:
    if question.state == 'bloqueada' and not dependencies:
        return [
            Finding(
                'state-dependency-mismatch',
                'estado bloqueada sem bloqueada-por',
                question=question.qid,
                line=question.line,
            )
        ]
    if question.state == 'bloqueada' and not open_targets:
        return [
            Finding(
                'state-dependency-mismatch',
                'estado bloqueada, mas toda dependencia ja e terminal',
                question=question.qid,
                line=question.line,
            )
        ]
    if question.state == 'fronteira' and open_targets:
        return [
            Finding(
                'state-dependency-mismatch',
                'estado fronteira com dependencia nao terminal: '
                + ', '.join(open_targets),
                question=question.qid,
                line=question.line,
            )
        ]
    if question.state in TERMINAL_STATES and open_targets:
        return [
            Finding(
                'state-dependency-mismatch',
                f'estado terminal {question.state} com dependencia '
                'nao terminal: ' + ', '.join(open_targets),
                question=question.qid,
                line=question.line,
            )
        ]
    return []


def computed_score(document: Document) -> dict[str, int]:
    """Count questions by state independently of the declared score."""
    score = dict.fromkeys(SCORE_COLUMNS.values(), 0)
    for question in document.questions:
        if question.state in score:
            score[question.state] += 1
    return score


def check_score(document: Document) -> list[Finding]:
    if 'placar' not in document.sections:
        return []
    if document.score_missing_columns:
        return [
            Finding(
                'score-columns-missing',
                'placar sem as colunas: '
                + ', '.join(document.score_missing_columns),
                line=document.score_line,
            )
        ]
    computed = computed_score(document)
    findings = [
        Finding(
            'score-mismatch',
            f'placar diz {document.score[state]} {label!r},'
            f' documento tem {computed[state]}',
            line=document.score_line,
        )
        for label, state in SCORE_COLUMNS.items()
        if document.score[state] != computed[state]
    ]
    total = sum(document.score.values())
    if total != len(document.questions):
        findings.append(
            Finding(
                'score-sum-mismatch',
                f'soma do placar {total} != {len(document.questions)} duvidas',
                line=document.score_line,
            )
        )
    return findings
