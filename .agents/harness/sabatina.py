#!/usr/bin/env python3
"""Valida o documento de sabatina da skill resolve-open-questions.

O julgamento sobre o conteudo continua com o agente. Este script cobre o que e
deterministico e se repete a cada rodada: ids, campos obrigatorios por estado,
referencias de `bloqueada-por`, ciclos no grafo, evidencia dos fatos, aritmetica
do placar e as pre-condicoes de confirmacao e de fechamento.

Fases:
  round             estrutura, estados, grafo e placar.
  pre-confirmation  round + fronteira/bloqueadas zeradas e entendimento escrito.
  closed            pre-confirmation + confirmacao datada, rascunhos e handoff.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

TERMINAL_STATES = frozenset(
    {'respondida', 'apurada', 'assumida', 'descartada'}
)
OPEN_STATES = frozenset({'fronteira', 'bloqueada'})
VALID_STATES = TERMINAL_STATES | OPEN_STATES

TERMINAL_FIELDS: dict[str, str] = {
    'respondida': 'resposta',
    'apurada': 'evidencia',
    'assumida': 'premissa',
    'descartada': 'descartada-por',
}

SCORE_COLUMNS: dict[str, str] = {
    'respondidas': 'respondida',
    'apuradas': 'apurada',
    'assumidas': 'assumida',
    'na fronteira': 'fronteira',
    'bloqueadas': 'bloqueada',
    'descartadas': 'descartada',
}

STATUS_OPEN = 'em andamento'
STATUS_AWAITING = 'aguardando confirmacao'
STATUS_CLOSED = 'fechada'
VALID_STATUS = frozenset({STATUS_OPEN, STATUS_AWAITING, STATUS_CLOSED})

PHASE_ROUND = 'round'
PHASE_PRE = 'pre-confirmation'
PHASE_CLOSED = 'closed'
PHASES = (PHASE_ROUND, PHASE_PRE, PHASE_CLOSED)

SECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ('placar', 'placar'),
    ('cobertura', 'cobertura'),
    ('fatos', 'fatos'),
    ('duvidas', 'duvidas'),
    ('entendimento', 'entendimento'),
    ('rascunhos', 'rascunhos'),
    ('handoff', 'handoff'),
    ('objetivo', 'objetivo'),
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

HANDOFF_ROUTE_SECTION = 'proximo workflow proposto'

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

OPENSPEC_CRITERIA: tuple[str, ...] = ROUTE_CRITERIA[:-1]
PLAN_CRITERION = ROUTE_CRITERIA[-1]

TRUE_ANSWERS = frozenset({'sim', 'yes', 'true'})
FALSE_ANSWERS = frozenset({'nao', 'no', 'false'})
DASHES = '\N{EM DASH}', '\N{EN DASH}'
NO_DEPENDENCY = frozenset(
    {'nenhuma', 'nenhum', 'none', '-', *DASHES, 'n/a', ''}
)
AGGREGATE_MARKERS: tuple[str, ...] = ('agregad',)
EMPTY_VALUES = frozenset({'', *DASHES, '-', 'n/a', 'na'})

SECTION_RE = re.compile(r'^##\s+(?:\d+\.\s*)?(.+?)\s*$')
SUBSECTION_RE = re.compile(r'^###\s+(?:\d+\.\s*)?(.+?)\s*$')
QUESTION_RE = re.compile(
    '^###\\s+(Q\\d+)\\s*[\\N{EM DASH}\\N{EN DASH}-]?\\s*(.*?)\\s*$'
)
FIELD_RE = re.compile(r'^\s*-\s+\*\*([^*]+)\*\*([^:]*?):(.*)$')
PLACEHOLDER_RE = re.compile(r'<[^<>\n]{3,}>')
TERMINAL_PLACEHOLDER_RE = re.compile(
    r'<[^<>\n]{3,}>|\b(?:tbd|todo|to be decided|fill me)\b',
    re.IGNORECASE,
)
QID_RE = re.compile(r'Q\d+')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
FACT_ID_RE = re.compile(r'^F\d+$')
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
NUMBERED_ADR_RE = re.compile(r'\badr(?:-draft)?-\d{4}\b', re.IGNORECASE)
DRAFT_PATH_RE = re.compile(
    r'^(?:docs/internal/sabatina/)?adr-draft/'
    r'adr-draft-[a-z0-9]+(?:-[a-z0-9]+)*\.md$',
    re.IGNORECASE,
)
SEPARATOR_CELL_RE = re.compile(r'^:?-{3,}:?$')
FIELD_LINE_RE = re.compile(r'^\s*-\s+\*\*([^*]+)\*\*\s*:\s*(.*?)\s*$')

ROUTE_CRITERION_KEYS: tuple[str, ...] = ROUTE_CRITERIA
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

UNIT_COLUMN_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('name', ('change', 'work unit', 'unidade')),
    ('owned', ('ids',)),
    ('objective', ('objetivo', 'objective')),
    ('acceptance', ('aceite', 'acceptance')),
    ('rollout', ('rollout',)),
    ('rollback', ('rollback',)),
    ('dependencies', ('depende', 'depends')),
)
AGGREGATE_FIELD_KEYS = frozenset({'aceite agregado', 'aggregate completion'})
AGGREGATE_UNIT_MARKERS: tuple[str, ...] = ('change', 'unidade', 'unit')
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


@dataclass(frozen=True)
class Finding:
    """Um defeito encontrado, com codigo estavel para teste e para o agente."""

    code: str
    message: str
    question: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            'code': self.code,
            'message': self.message,
            'question': self.question,
            'line': self.line,
        }


@dataclass
class Section:
    """Bloco `##` do documento, guardado com a linha em que comeca."""

    key: str
    title: str
    line: int
    body: list[tuple[int, str]] = field(default_factory=list)

    def text(self) -> str:
        return '\n'.join(content for _, content in self.body).strip()


@dataclass
class Question:
    """Uma duvida `Qn` e os campos declarados no seu bloco."""

    qid: str
    title: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)

    def value(self, key: str) -> str:
        return self.fields.get(key, '').strip()

    def has(self, key: str) -> bool:
        return not _is_empty(self.value(key))

    def has_prefixed(self, prefix: str) -> bool:
        return any(
            name == prefix or name.startswith(f'{prefix} ')
            for name, value in self.fields.items()
            if not _is_empty(value)
        )

    def prefixed_value(self, prefix: str) -> str:
        for name, value in self.fields.items():
            matches = name == prefix or name.startswith(f'{prefix} ')
            if matches and not _is_empty(value):
                return value.strip()
        return ''

    @property
    def state(self) -> str:
        return _norm(self.value('estado'))

    @property
    def dependencies(self) -> list[str]:
        return QID_RE.findall(self.value('bloqueada-por'))


@dataclass
class Document:
    """Estado parseado do documento, sem nenhum julgamento aplicado."""

    path: Path
    status: str = ''
    confirmed_on: str = ''
    sections: dict[str, Section] = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)
    duplicated_ids: list[str] = field(default_factory=list)
    facts: list[tuple[int, str, str]] = field(default_factory=list)
    score: dict[str, int] = field(default_factory=dict)
    score_line: int | None = None
    score_missing_columns: list[str] = field(default_factory=list)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize('NFD', text)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def _norm(text: str) -> str:
    return _strip_accents(text).strip().lower()


def _is_empty(value: str) -> bool:
    return _norm(value) in EMPTY_VALUES


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_RE.search(value))


def _is_terminal_placeholder(value: str) -> bool:
    return bool(TERMINAL_PLACEHOLDER_RE.search(value))


def _repository_root() -> Path:
    """Raiz do repositorio, derivada do proprio script e nao do documento."""
    for candidate in [Path.cwd(), *Path.cwd().resolve().parents]:
        if (candidate / '.git').exists():
            return candidate
    return Path.cwd()


def _is_repository_path(token: str) -> bool:
    """Aceita apenas caminho relativo que existe dentro deste repositorio."""
    if not PATH_TOKEN_RE.match(token):
        return False
    target = token.split(':', 1)[0]
    if not target or target.startswith('/'):
        return False
    parts = PurePosixPath(target).parts
    if not parts or '..' in parts or parts == ('.',):
        return False
    root = _repository_root().resolve()
    candidate = (root / target).resolve()
    return candidate.is_relative_to(root) and candidate.exists()


def _records_result(token: str, context: str) -> bool:
    """Aceita somente formas fechadas de resultado terminal registrado."""
    normalized = _norm(context)
    normalized_token = re.escape(_norm(token))
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
    """Comando so vale como fonte quando o resultado dele esta registrado."""
    words = token.split()
    return (
        bool(words)
        and words[0] in COMMAND_HEADS
        and _records_result(token, context)
    )


def _has_resolvable_source(text: str) -> bool:
    """Aceita apenas caminho do repositorio, comando registrado ou URL."""
    if URL_RE.search(text):
        return True
    return any(
        _is_repository_path(token.strip()) or _is_recorded_command(token, text)
        for token in INLINE_CODE_RE.findall(text)
    )


def _split_cells(row: str) -> list[str]:
    """Divide a linha em celulas sem quebrar dentro de trechos em crase."""
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for char in row.strip().strip('|'):
        if char == '`':
            in_code = not in_code
        if char == '|' and not in_code:
            cells.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append(''.join(current).strip())
    return cells


def _table_rows(body: list[tuple[int, str]]) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    for number, content in body:
        stripped = content.strip()
        if not stripped.startswith('|'):
            continue
        cells = _split_cells(stripped)
        if all(SEPARATOR_CELL_RE.match(cell) for cell in cells if cell):
            continue
        rows.append((number, cells))
    return rows


def _section_key(title: str) -> str | None:
    normalized = _norm(title)
    for marker, key in SECTION_MARKERS:
        if marker in normalized:
            return key
    return None


def _parse_header(lines: list[str], document: Document) -> None:
    for content in lines:
        if content.startswith('## '):
            return
        if not content.startswith('>'):
            continue
        raw = content.lstrip('> ').strip()
        key, _, value = raw.partition(':')
        normalized = _norm(key)
        if normalized == 'status':
            document.status = _norm(value)
        elif normalized == 'confirmada em':
            document.confirmed_on = value.strip()


def _parse_sections(lines: list[str], document: Document) -> None:
    current: Section | None = None
    for index, content in enumerate(lines, start=1):
        match = SECTION_RE.match(content)
        if match:
            key = _section_key(match.group(1))
            current = Section(key=key or '', title=match.group(1), line=index)
            if key and key not in document.sections:
                document.sections[key] = current
            continue
        if current is not None:
            current.body.append((index, content))


def _flush_field(
    question: Question | None, name: str, buffer: list[str]
) -> None:
    if question is None or not name:
        return
    question.fields[name] = ' '.join(part.strip() for part in buffer).strip()


def _parse_questions(document: Document) -> None:
    section = document.sections.get('duvidas')
    if section is None:
        return
    seen: set[str] = set()
    current: Question | None = None
    name = ''
    buffer: list[str] = []
    for number, content in section.body:
        match = QUESTION_RE.match(content)
        if match:
            _flush_field(current, name, buffer)
            name, buffer = '', []
            current = Question(
                qid=match.group(1), title=match.group(2), line=number
            )
            if current.qid in seen:
                document.duplicated_ids.append(current.qid)
            seen.add(current.qid)
            document.questions.append(current)
            continue
        field_match = FIELD_RE.match(content)
        if field_match:
            _flush_field(current, name, buffer)
            name = _norm(field_match.group(1))
            buffer = [field_match.group(3)]
            continue
        if buffer and content.startswith((' ', '\t')):
            buffer.append(content)
    _flush_field(current, name, buffer)


def _parse_score(document: Document) -> None:
    section = document.sections.get('placar')
    if section is None:
        return
    rows = _table_rows(section.body)
    if len(rows) < 2:
        return
    header_line, header = rows[0]
    _, values = rows[1]
    document.score_line = header_line
    for index, label in enumerate(header):
        state = SCORE_COLUMNS.get(_norm(label))
        if state is None or index >= len(values):
            continue
        raw = values[index].strip()
        if raw.isdigit():
            document.score[state] = int(raw)


def _parse_facts(document: Document) -> None:
    section = document.sections.get('fatos')
    if section is None:
        return
    for number, cells in _table_rows(section.body):
        if len(cells) < 3 or not FACT_ID_RE.match(cells[0]):
            continue
        document.facts.append((number, cells[0], cells[-1]))


def parse_document(path: Path) -> Document:
    """Le o arquivo e devolve o modelo parseado, sem validar nada."""
    lines = path.read_text(encoding='utf-8').splitlines()
    document = Document(path=path)
    _parse_header(lines, document)
    _parse_sections(lines, document)
    _parse_questions(document)
    _parse_score(document)
    _parse_facts(document)
    document.score_missing_columns = [
        label
        for label, state in SCORE_COLUMNS.items()
        if state not in document.score
    ]
    return document


def _required_sections(phase: str) -> tuple[str, ...]:
    required = ('placar', 'cobertura', 'fatos', 'duvidas')
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
    if not DATE_RE.search(document.confirmed_on):
        findings.append(
            Finding(
                'confirmation-missing',
                'cabecalho sem "Confirmada em: AAAA-MM-DD"',
            )
        )
    return findings


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
    if not value or not _is_terminal_placeholder(value):
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
    premise = _norm(question.value('premissa'))
    if not premise:
        return [
            Finding(
                'field-missing',
                'estado assumida exige o campo premissa',
                question=question.qid,
                line=question.line,
            )
        ]
    missing = [
        marker
        for marker in ('valida com:', 'reabre quando:')
        if marker not in premise
    ]
    return [
        Finding(
            'premise-incomplete',
            f'premissa sem {marker!r}',
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


def check_references(document: Document) -> list[Finding]:
    """Prova que cada referencia terminal aponta para algo que existe."""
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
    if _is_empty(evidence):
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
    if FACT_REF_RE.search(evidence) or _has_resolvable_source(evidence):
        return []
    return [
        Finding(
            'evidence-unresolved',
            'evidencia sem fato Fn, caminho, comando ou URL verificavel',
            question=question.qid,
            line=question.line,
        )
    ]


def _dependency_edges(document: Document) -> dict[str, list[str]]:
    return {
        question.qid: question.dependencies for question in document.questions
    }


def _find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
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
    cycle = _find_cycle(edges)
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
    """Contagem real por estado, base de comparacao com a tabela do placar."""
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


def check_facts(document: Document) -> list[Finding]:
    findings: list[Finding] = []
    for number, fact_id, evidence in document.facts:
        if _is_empty(evidence) or _is_placeholder(evidence):
            findings.append(
                Finding(
                    'fact-evidence-missing',
                    f'{fact_id} sem evidencia registrada',
                    line=number,
                )
            )
        elif not _has_resolvable_source(evidence):
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
        for _, cells in _table_rows(section.body)
        if len(cells) >= 2 and _norm(cells[0]) != 'eixo'
    ]
    findings = _check_coverage_axes(rows, section.line)
    findings.extend(
        Finding(
            'coverage-placeholder',
            f'eixo {cells[0]!r} ainda com texto de template',
            line=section.line,
        )
        for cells in rows
        if _is_placeholder(cells[1]) or _is_empty(cells[1])
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
        normalized = _norm(result)
        if normalized.startswith('nao se aplica:'):
            rationale = normalized.split(':', 1)[1].strip()
            if not rationale or _is_placeholder(result):
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
    """A cobertura vale os oito eixos exatos da checklist, sem sinonimo."""
    declared = [_norm(cells[0]) for cells in rows]
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
    if not text or _is_placeholder(text):
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
        for number, cells in _table_rows(section.body)
        if cells
        and _norm(cells[0]) != 'rascunho'
        and not _is_placeholder(cells[0])
        and not _is_empty(cells[0])
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
            current = _norm(match.group(1))
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
        elif not body.strip() or _is_placeholder(body):
            findings.append(
                Finding(
                    'handoff-unfilled',
                    f'secao {name!r} do handoff vazia ou de template',
                )
            )
    return findings


@dataclass(frozen=True)
class RouteDecision:
    """Rota recomendada, ou os criterios que faltam para decidir."""

    route: str | None
    unmet: tuple[str, ...]


@dataclass(frozen=True)
class Unit:
    """Uma linha da tabela de decomposicao do handoff."""

    name: str
    line: int
    owned: tuple[str, ...]
    objective: str
    acceptance: str
    rollout: str
    rollback: str
    dependencies: tuple[str, ...]
    cells: tuple[str, ...]


def classify_route(answers: dict[str, bool | None]) -> RouteDecision:
    """Menor rota que preserva o contrato. Nao inicia o que escolheu.

    Criterio nao declarado nunca vira preferencia do agente: a decisao
    volta com a lista do que falta.
    """
    unmet = tuple(name for name in ROUTE_CRITERIA if answers.get(name) is None)
    if unmet:
        return RouteDecision(route=None, unmet=unmet)
    if any(answers[name] for name in OPENSPEC_CRITERIA):
        return RouteDecision(route=ROUTE_OPENSPEC, unmet=())
    if answers[PLAN_CRITERION]:
        return RouteDecision(route=ROUTE_PLAN, unmet=())
    return RouteDecision(route=ROUTE_DIRECT, unmet=())


def _strip_code(value: str) -> str:
    return value.replace('`', '').strip()


def _tables(
    body: list[tuple[int, str]],
) -> list[list[tuple[int, list[str]]]]:
    tables: list[list[tuple[int, list[str]]]] = []
    current: list[tuple[int, list[str]]] = []
    for number, content in body:
        stripped = content.strip()
        if not stripped.startswith('|'):
            if current:
                tables.append(current)
                current = []
            continue
        cells = _split_cells(stripped)
        if all(SEPARATOR_CELL_RE.match(cell) for cell in cells if cell):
            continue
        current.append((number, cells))
    if current:
        tables.append(current)
    return tables


def _subsection_body(
    document: Document, section_key: str, wanted: str
) -> list[tuple[int, str]]:
    section = document.sections.get(section_key)
    if section is None:
        return []
    body: list[tuple[int, str]] = []
    inside = False
    for number, content in section.body:
        match = SUBSECTION_RE.match(content)
        if match:
            inside = _norm(match.group(1)) == wanted
            continue
        if inside:
            body.append((number, content))
    return body


def _find_table(
    tables: list[list[tuple[int, list[str]]]], marker: str
) -> list[tuple[int, list[str]]] | None:
    for table in tables:
        _, header = table[0]
        if any(marker in _norm(cell) for cell in header):
            return table
    return None


def _column_index(header: list[str], marker: str) -> int:
    for index, cell in enumerate(header):
        if marker in _norm(cell):
            return index
    return -1


def _declared_routes(text: str) -> set[str]:
    return {
        route
        for route, markers in ROUTE_MARKERS.items()
        if any(marker in text for marker in markers)
    }


def _route_value(table: list[tuple[int, list[str]]], key: str) -> str:
    wanted = _norm(key)
    for _, cells in table[1:]:
        if cells and _norm(cells[0]) == wanted and len(cells) >= 2:
            return _norm(cells[1])
    return ''


def _route_from_value(value: str) -> str | None:
    normalized = _norm(value)
    return ROUTE_ALIASES.get(normalized)


def _route_matrix_keys(
    table: list[tuple[int, list[str]]],
) -> tuple[set[str], dict[str, int]]:
    declared: set[str] = set()
    counts: dict[str, int] = {}
    for _, cells in table[1:]:
        if not cells:
            continue
        key = _norm(cells[0])
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
        value = _norm(cells[1])
        if value in TRUE_ANSWERS:
            answers[_norm(cells[0])] = True
        elif value in FALSE_ANSWERS:
            answers[_norm(cells[0])] = False
        else:
            answers[_norm(cells[0])] = None
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
    required = set(ROUTE_CRITERION_KEYS)
    findings = [
        Finding(
            'route-criterion-missing',
            'matriz de rota sem o criterio ' + repr(criterion),
            line=line,
        )
        for criterion in ROUTE_CRITERION_KEYS
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

    declared_route = _route_from_value(
        _route_value(table, ROUTE_RECOMMENDATION_KEY)
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
    authorization = _route_value(table, ROUTE_AUTHORIZATION_KEY)
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
    """A rota e recomendada e recalculavel; inicia-la e outro ato."""
    body = _subsection_body(document, 'handoff', HANDOFF_ROUTE_SECTION)
    if not body:
        return []
    text = _norm('\n'.join(content for _, content in body))
    findings = _check_route_declaration(text, body[0][0])
    criteria = _find_table(_tables(body), 'criterio')
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


def _dependency_names(raw: str) -> list[str]:
    cleaned = _strip_code(raw)
    if _norm(cleaned) in NO_DEPENDENCY:
        return []
    return [
        _strip_code(part)
        for part in cleaned.split(',')
        if _norm(_strip_code(part)) not in NO_DEPENDENCY
    ]


def _unit_column_indices(header: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for key, markers in UNIT_COLUMN_MARKERS:
        for index, cell in enumerate(header):
            normalized = _norm(cell)
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


def _check_unit_cells(unit: Unit) -> list[Finding]:
    incomplete = any(
        _is_empty(cell) or _is_placeholder(cell) for cell in unit.cells
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
            if _is_empty(value) or _is_placeholder(value):
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
    cycle = _find_cycle({unit.name: list(unit.dependencies) for unit in units})
    if cycle is not None:
        findings.append(
            Finding(
                'decomposition-cycle',
                'ciclo entre changes: ' + ' -> '.join(cycle),
            )
        )
    return findings


def _check_aggregate(
    units: list[Unit], body: list[tuple[int, str]]
) -> list[Finding]:
    if not units:
        return []
    value = ''
    for _, content in body:
        match = FIELD_LINE_RE.match(content)
        if match and _norm(match.group(1)) in AGGREGATE_FIELD_KEYS:
            value = match.group(2).strip()
            break
    if not value or _is_placeholder(value):
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
    """Aceite agregado precisa cobrir todas as unidades e afirmar aceite."""
    normalized = _norm(value)
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
    names = [_norm(unit.name) for unit in units]
    if all(name and name in normalized for name in names):
        return True
    if _declared_unit_count(normalized) == len(units):
        return True
    return any(marker in normalized for marker in AGGREGATE_ALL_MARKERS)


def _states_acceptance(normalized: str) -> bool:
    return '?' not in normalized and bool(
        AGGREGATE_ACCEPTANCE_RE.match(normalized)
    )


def check_decomposition(document: Document) -> list[Finding]:
    """Zero, uma ou N unidades; cada decisao com um unico dono."""
    body = _subsection_body(document, 'handoff', HANDOFF_ROUTE_SECTION)
    if not body:
        return []
    route_table = _find_table(_tables(body), 'criterio')
    declared_route = (
        _route_from_value(_route_value(route_table, ROUTE_RECOMMENDATION_KEY))
        if route_table is not None
        else None
    )
    table = _find_table(_tables(body), 'ids')
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
    findings.extend(_check_aggregate(units, body))
    return findings


def validate(document: Document, phase: str) -> list[Finding]:
    """Aplica as checagens da fase pedida, cumulativas por definicao."""
    findings = check_structure(document, phase)
    findings += check_status(document, phase)
    findings += check_questions(document)
    findings += check_references(document)
    findings += check_graph(document)
    findings += check_score(document)
    findings += check_facts(document)
    findings += check_coverage(document)
    if phase in (PHASE_PRE, PHASE_CLOSED):
        findings += check_closure(document)
        findings += check_understanding(document)
        findings += check_drafts(document, phase)
    if phase == PHASE_CLOSED:
        findings += check_handoff(document)
        findings += check_route(document)
        findings += check_decomposition(document)
    return findings


def build_report(
    document: Document, phase: str, findings: list[Finding]
) -> dict[str, object]:
    return {
        'status': 'error' if findings else 'ok',
        'phase': phase,
        'document': str(document.path),
        'question_count': len(document.questions),
        'score': computed_score(document),
        'errors': [finding.as_dict() for finding in findings],
    }


def _print_human(
    document: Document, phase: str, findings: list[Finding]
) -> None:
    for finding in findings:
        where = finding.question or finding.line or '-'
        print(f'error [{finding.code}] {where}: {finding.message}')
    summary = ' '.join(
        f'{name}={count}' for name, count in computed_score(document).items()
    )
    verdict = 'FALHOU' if findings else 'OK'
    print(
        f'{verdict} fase={phase} duvidas={len(document.questions)} {summary}'
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Valida um documento de sabatina.'
    )
    parser.add_argument('--document', required=True)
    parser.add_argument('--phase', choices=PHASES, default=PHASE_ROUND)
    parser.add_argument('--json', action='store_true')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.document)
    if not path.is_file():
        print(f'error [document-missing] {path}: arquivo nao encontrado')
        return 2
    document = parse_document(path)
    findings = validate(document, args.phase)
    if args.json:
        report = build_report(document, args.phase, findings)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(document, args.phase, findings)
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
