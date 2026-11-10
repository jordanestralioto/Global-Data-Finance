"""Validate phase prerequisites, ADR drafts and handoff completeness."""

from __future__ import annotations

import re

from harness.sabatina.document import (
    PHASE_CLOSED,
    PHASE_PRE,
    PHASE_ROUND,
    STATUS_AWAITING,
    STATUS_CLOSED,
    VALID_STATUS,
    Document,
    Finding,
    valid_date,
)
from harness.sabatina.markdown import (
    SUBSECTION_RE,
    is_empty,
    is_placeholder,
    is_terminal_placeholder,
    normalize,
    table_rows,
)
from harness.sabatina.questions import (
    computed_score,
)

HANDOFF_SECTIONS: tuple[str, ...] = (
    'objetivo',
    'decisoes e alternativas',
    'fatos com evidencia',
    'premissas e gatilhos',
    'invariantes',
    'criterios de aceite',
    'artefatos',
    'proximo workflow proposto',
)


NUMBERED_ADR_RE = re.compile(r'\badr(?:-draft)?-\d{4}\b', re.IGNORECASE)


DRAFT_PATH_RE = re.compile(
    r'^(?:docs/internal/sabatina/)?adr-draft/'
    r'adr-draft-[a-z0-9]+(?:-[a-z0-9]+)*\.md$',
    re.IGNORECASE,
)


def _required_sections(phase: str) -> tuple[str, ...]:
    required = ('objetivo', 'placar', 'cobertura', 'fatos', 'duvidas')
    if phase == PHASE_ROUND:
        return required
    if phase == PHASE_PRE:
        return (*required, 'entendimento')
    return (*required, 'entendimento', 'rascunhos', 'handoff')


def check_structure(document: Document, phase: str) -> list[Finding]:
    findings = [
        Finding(
            'section-missing',
            f'secao obrigatoria ausente para a fase {phase}: {key}',
        )
        for key in _required_sections(phase)
        if key not in document.sections
    ]
    objective = document.sections.get('objetivo')
    if objective is not None and (
        is_empty(objective.text()) or is_terminal_placeholder(objective.text())
    ):
        findings.append(
            Finding(
                'objective-unfilled',
                'objetivo vazio ou com texto de template',
                line=objective.line,
            )
        )
    if not document.questions and 'duvidas' in document.sections:
        findings.append(
            Finding('questions-missing', 'nenhuma duvida Qn registrada')
        )
    findings.extend(
        Finding('question-duplicate', f'id repetido: {qid}', question=qid)
        for qid in document.duplicated_ids
    )
    return findings


def check_status(document: Document, phase: str) -> list[Finding]:
    findings: list[Finding] = []
    if document.status not in VALID_STATUS:
        findings.append(
            Finding(
                'status-invalid',
                f'status {document.status!r} fora de {sorted(VALID_STATUS)}',
            )
        )
    if phase == PHASE_PRE and document.status != STATUS_AWAITING:
        findings.append(
            Finding(
                'status-phase-mismatch',
                f'fase {phase} exige status {STATUS_AWAITING!r}',
            )
        )
    if phase == PHASE_CLOSED:
        findings.extend(_check_closed_status(document, phase))
    return findings


def _check_closed_status(document: Document, phase: str) -> list[Finding]:
    findings: list[Finding] = []
    if document.status != STATUS_CLOSED:
        findings.append(
            Finding(
                'status-phase-mismatch',
                f'fase {phase} exige status {STATUS_CLOSED!r}',
            )
        )
    if not valid_date(document.confirmed_on):
        findings.append(
            Finding(
                'confirmation-missing',
                'cabecalho sem "Confirmada em: AAAA-MM-DD" valido',
            )
        )
    return findings


def check_closure(document: Document) -> list[Finding]:
    computed = computed_score(document)
    return [
        Finding(
            f'{state}-not-empty',
            f'{computed[state]} duvida(s) em estado {state}',
        )
        for state in ('fronteira', 'bloqueada')
        if computed[state] > 0
    ]


def check_understanding(document: Document) -> list[Finding]:
    section = document.sections.get('entendimento')
    if section is None:
        return []
    text = section.text()
    if not text or is_placeholder(text):
        return [
            Finding(
                'understanding-unfilled',
                'entendimento consolidado vazio ou com texto de template',
                line=section.line,
            )
        ]
    return []


def _draft_rows(document: Document) -> list[tuple[int, str]]:
    section = document.sections.get('rascunhos')
    if section is None:
        return []
    return [
        (number, cells[0])
        for number, cells in table_rows(section.body)
        if cells
        and normalize(cells[0]) != 'rascunho'
        and not is_placeholder(cells[0])
        and not is_empty(cells[0])
    ]


def check_drafts(document: Document, phase: str) -> list[Finding]:
    rows = _draft_rows(document)
    if phase == PHASE_PRE:
        return [
            Finding(
                'draft-premature',
                f'rascunho {name} listado antes da confirmacao',
                line=number,
            )
            for number, name in rows
        ]
    findings: list[Finding] = []
    for number, name in rows:
        path = name.strip().strip('`')
        if NUMBERED_ADR_RE.search(path):
            findings.append(
                Finding(
                    'draft-numbered',
                    f'rascunho {name} ja recebeu numero NNNN',
                    line=number,
                )
            )
        elif not DRAFT_PATH_RE.fullmatch(path):
            findings.append(
                Finding(
                    'draft-path-invalid',
                    f'rascunho {name} fora do caminho ADR draft canonico',
                    line=number,
                )
            )
    return findings


def _handoff_subsections(document: Document) -> dict[str, str]:
    section = document.sections.get('handoff')
    if section is None:
        return {}
    found: dict[str, str] = {}
    current = ''
    for _, content in section.body:
        match = SUBSECTION_RE.match(content)
        if match:
            current = normalize(match.group(1))
            found[current] = ''
            continue
        if current:
            found[current] = f'{found[current]}\n{content}'
    return found


def check_handoff(document: Document) -> list[Finding]:
    if 'handoff' not in document.sections:
        return []
    found = _handoff_subsections(document)
    findings: list[Finding] = []
    for name in HANDOFF_SECTIONS:
        body = found.get(name)
        if body is None:
            findings.append(
                Finding(
                    'handoff-incomplete',
                    f'handoff sem a secao {name!r}',
                )
            )
        elif not body.strip() or is_placeholder(body):
            findings.append(
                Finding(
                    'handoff-unfilled',
                    f'secao {name!r} do handoff vazia ou de template',
                )
            )
    return findings
