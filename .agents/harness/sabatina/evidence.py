"""Validate evidence sources, decision references and coverage."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from harness.paths import repo_root
from harness.sabatina.document import (
    QID_RE,
    TERMINAL_STATES,
    Document,
    Finding,
    Question,
)
from harness.sabatina.markdown import (
    is_empty,
    is_placeholder,
    normalize,
    table_rows,
)
from harness.sabatina.questions import dependency_cycle

COVERAGE_AXES: tuple[str, ...] = (
    'escopo',
    'consumidores',
    'contratos e dados',
    'falhas e seguranca',
    'migracao e rollback',
    'operacao e observabilidade',
    'validacao',
    'ownership e documentacao',
)


FACT_REF_RE = re.compile(r'\bF\d+\b')


INLINE_CODE_RE = re.compile(r'`([^`\n]+)`')


URL_RE = re.compile(r'https?://\S+')


PATH_TOKEN_RE = re.compile(r'^[\w./@-]+(?::\d+(?:-\d+)?)?$')


COMMAND_HEADS = frozenset(
    {
        'bash',
        'cat',
        'git',
        'grep',
        'ls',
        'mypy',
        'node',
        'npm',
        'npx',
        'pre-commit',
        'pytest',
        'python',
        'python3',
        'rg',
        'ruff',
        'sh',
        'test',
        'uv',
    }
)


EXPLICIT_COMMAND_RESULT_RE = re.compile(
    r'^resultado registrado:\s*`[^`\n]+`\s+'
    r'(?:passou|falhou)[.!]?$'
)


DATED_AUDIT_RESULT_RE = re.compile(
    r'^auditoria da branch em\s+\d{4}-\d{2}-\d{2}:\s+'
    r'(?:\d+\s+testes focados passaram;\s+)?'
    r'(?:'
    r'`[^`\n]+`\s+passou|'
    r'`[^`\n]+`(?:,\s*`[^`\n]+`)*\s+e\s+`[^`\n]+`\s+passaram'
    r')[.!]?$'
)


def _is_repository_path(token: str) -> bool:
    """Accept an existing relative path contained in the target repository."""
    if not PATH_TOKEN_RE.match(token):
        return False
    target = token.split(':', 1)[0]
    if not target or target.startswith('/'):
        return False
    parts = PurePosixPath(target).parts
    if not parts or '..' in parts or parts == ('.',):
        return False
    root = repo_root().resolve()
    candidate = (root / target).resolve()
    return candidate.is_relative_to(root) and candidate.exists()


def _records_result(token: str, context: str) -> bool:
    """Accept only explicit recorded terminal command outcomes."""
    normalized = normalize(context)
    normalized_token = re.escape(normalize(token))
    terminal_exit = re.fullmatch(
        r'(?:`[\w./@:-]+`;\s*)?'
        r'(?:em\s+\d{4}-\d{2}-\d{2},?\s+)?o comando\s+'
        rf'`{normalized_token}`\s+(?:terminou|retornou)\s+com\s+'
        r'exit code\s+-?\d+\s*[.!]?$',
        normalized,
    )
    return bool(
        terminal_exit
        or EXPLICIT_COMMAND_RESULT_RE.fullmatch(normalized)
        or DATED_AUDIT_RESULT_RE.fullmatch(normalized)
    )


def _is_recorded_command(token: str, context: str) -> bool:
    """A command is a source only when its outcome is recorded."""
    words = token.split()
    return (
        bool(words)
        and words[0] in COMMAND_HEADS
        and _records_result(token, context)
    )


def has_resolvable_source(text: str) -> bool:
    """Accept repository paths, recorded commands or URLs."""
    if URL_RE.search(text):
        return True
    return any(
        _is_repository_path(token.strip()) or _is_recorded_command(token, text)
        for token in INLINE_CODE_RE.findall(text)
    )


def check_references(document: Document) -> list[Finding]:
    """Check that terminal references resolve to existing facts or decisions."""
    question_states = {
        question.qid: question.state for question in document.questions
    }
    known_facts = {fact_id for _, fact_id, _ in document.facts}
    findings: list[Finding] = []
    for question in document.questions:
        if question.state == 'descartada':
            findings.extend(
                _check_discard_reference(question, question_states)
            )
        elif question.state == 'apurada':
            findings.extend(_check_evidence_source(question, known_facts))
    discards = {
        question.qid: QID_RE.findall(question.value('descartada-por'))
        if question.state == 'descartada'
        else []
        for question in document.questions
    }
    cycle = dependency_cycle(discards)
    if cycle is not None:
        findings.append(
            Finding(
                'discard-reference-cycle',
                'ciclo em descartada-por: ' + ' -> '.join(cycle),
            )
        )
    return findings


def _check_discard_reference(
    question: Question, states: dict[str, str]
) -> list[Finding]:
    findings: list[Finding] = []
    for target in QID_RE.findall(question.value('descartada-por')):
        if target == question.qid:
            findings.append(
                Finding(
                    'discard-reference-self',
                    'descartada-por aponta para a propria duvida',
                    question=question.qid,
                    line=question.line,
                )
            )
        elif target not in states:
            findings.append(
                Finding(
                    'discard-reference-unknown',
                    f'descartada-por aponta para {target}, que nao existe',
                    question=question.qid,
                    line=question.line,
                )
            )
        elif states[target] not in TERMINAL_STATES:
            findings.append(
                Finding(
                    'discard-reference-not-terminal',
                    'descartada-por aponta para '
                    f'{target}, que ainda nao e terminal',
                    question=question.qid,
                    line=question.line,
                )
            )
    return findings


def _check_evidence_source(
    question: Question, known_facts: set[str]
) -> list[Finding]:
    evidence = question.value('evidencia')
    if is_empty(evidence):
        return []
    unknown = [
        ref for ref in FACT_REF_RE.findall(evidence) if ref not in known_facts
    ]
    if unknown:
        return [
            Finding(
                'evidence-fact-unknown',
                'evidencia cita fato inexistente: ' + ', '.join(unknown),
                question=question.qid,
                line=question.line,
            )
        ]
    if FACT_REF_RE.search(evidence) or has_resolvable_source(evidence):
        return []
    return [
        Finding(
            'evidence-unresolved',
            'evidencia sem fato Fn, caminho, comando ou URL verificavel',
            question=question.qid,
            line=question.line,
        )
    ]


def check_facts(document: Document) -> list[Finding]:
    findings: list[Finding] = []
    for number, fact_id, evidence in document.facts:
        if is_empty(evidence) or is_placeholder(evidence):
            findings.append(
                Finding(
                    'fact-evidence-missing',
                    f'{fact_id} sem evidencia registrada',
                    line=number,
                )
            )
        elif not has_resolvable_source(evidence):
            findings.append(
                Finding(
                    'fact-evidence-unresolved',
                    f'{fact_id} sem caminho, comando ou URL verificavel',
                    line=number,
                )
            )
    return findings


def check_coverage(document: Document) -> list[Finding]:
    section = document.sections.get('cobertura')
    if section is None:
        return []
    rows = [
        cells
        for _, cells in table_rows(section.body)
        if len(cells) >= 2 and normalize(cells[0]) != 'eixo'
    ]
    findings = _check_coverage_axes(rows, section.line)
    findings.extend(
        Finding(
            'coverage-placeholder',
            f'eixo {cells[0]!r} ainda com texto de template',
            line=section.line,
        )
        for cells in rows
        if is_placeholder(cells[1]) or is_empty(cells[1])
    )
    findings.extend(_check_coverage_references(document, rows, section.line))
    return findings


def _check_coverage_references(
    document: Document, rows: list[list[str]], line: int
) -> list[Finding]:
    """Require a traceable decision/fact or an explicit inapplicability reason."""
    known_questions = {question.qid for question in document.questions}
    known_facts = {fact_id for _, fact_id, _ in document.facts}
    findings: list[Finding] = []
    for cells in rows:
        axis, result = cells[0], cells[1]
        normalized = normalize(result)
        if normalized.startswith('nao se aplica:'):
            rationale = normalized.split(':', 1)[1].strip()
            if not rationale or is_placeholder(result):
                findings.append(
                    Finding(
                        'coverage-inapplicable-unreasoned',
                        f'eixo {axis!r} sem razao apos nao se aplica:',
                        line=line,
                    )
                )
            continue
        question_refs = QID_RE.findall(result)
        fact_refs = FACT_REF_RE.findall(result)
        if not question_refs and not fact_refs:
            findings.append(
                Finding(
                    'coverage-reference-missing',
                    f'eixo {axis!r} sem Qn, Fn ou nao se aplica: razao',
                    line=line,
                )
            )
            continue
        findings.extend(
            Finding(
                'coverage-question-unknown',
                f'eixo {axis!r} cita duvida inexistente: {reference}',
                line=line,
            )
            for reference in question_refs
            if reference not in known_questions
        )
        findings.extend(
            Finding(
                'coverage-fact-unknown',
                f'eixo {axis!r} cita fato inexistente: {reference}',
                line=line,
            )
            for reference in fact_refs
            if reference not in known_facts
        )
    return findings


def _check_coverage_axes(rows: list[list[str]], line: int) -> list[Finding]:
    """Require exactly the eight declared coverage axes."""
    declared = [normalize(cells[0]) for cells in rows]
    findings = [
        Finding(
            'coverage-axis-missing',
            f'cobertura sem o eixo {axis!r}',
            line=line,
        )
        for axis in COVERAGE_AXES
        if axis not in declared
    ]
    findings.extend(
        Finding(
            'coverage-axis-unknown',
            f'eixo {axis!r} fora dos oito da checklist',
            line=line,
        )
        for axis in dict.fromkeys(declared)
        if axis not in COVERAGE_AXES
    )
    findings.extend(
        Finding(
            'coverage-axis-duplicate',
            f'eixo {axis!r} declarado mais de uma vez',
            line=line,
        )
        for axis in dict.fromkeys(declared)
        if declared.count(axis) > 1
    )
    return findings
