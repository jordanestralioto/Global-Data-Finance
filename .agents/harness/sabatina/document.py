"""Parse sabatina documents and expose their typed records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from harness.sabatina.markdown import (
    SUBSECTION_RE,
    is_empty,
    normalize,
    table_rows,
)

TERMINAL_STATES = frozenset(
    {'respondida', 'apurada', 'assumida', 'descartada'}
)


OPEN_STATES = frozenset({'fronteira', 'bloqueada'})


VALID_STATES = TERMINAL_STATES | OPEN_STATES


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


SECTION_RE = re.compile(r'^##\s+(?:\d+\.\s*)?(.+?)\s*$')


QUESTION_RE = re.compile(
    '^###\\s+(Q\\d+)\\s*[\\N{EM DASH}\\N{EN DASH}-]?\\s*(.*?)\\s*$'
)


FIELD_RE = re.compile(r'^\s*-\s+\*\*([^*]+)\*\*([^:]*?):(.*)$')


QID_RE = re.compile(r'Q\d+')


FACT_ID_RE = re.compile(r'^F\d+$')


@dataclass(frozen=True)
class Finding:
    """A validation error with a stable diagnostic code."""

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
    """A level-two section and its source line."""

    key: str
    title: str
    line: int
    body: list[tuple[int, str]] = field(default_factory=list)

    def text(self) -> str:
        return '\n'.join(content for _, content in self.body).strip()


@dataclass
class Question:
    """A question identifier and the fields declared in its block."""

    qid: str
    title: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)
    answered_on: str = ''

    def value(self, key: str) -> str:
        return self.fields.get(key, '').strip()

    def has(self, key: str) -> bool:
        return not is_empty(self.value(key))

    def has_prefixed(self, prefix: str) -> bool:
        return any(
            name == prefix or name.startswith(f'{prefix} ')
            for name, value in self.fields.items()
            if not is_empty(value)
        )

    def prefixed_value(self, prefix: str) -> str:
        for name, value in self.fields.items():
            matches = name == prefix or name.startswith(f'{prefix} ')
            if matches and not is_empty(value):
                return value.strip()
        return ''

    @property
    def state(self) -> str:
        return normalize(self.value('estado'))

    @property
    def dependencies(self) -> list[str]:
        return QID_RE.findall(self.value('bloqueada-por'))


@dataclass
class Document:
    """Parsed document state without validation results."""

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


def _section_key(title: str) -> str | None:
    normalized = normalize(title)
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
        normalized = normalize(key)
        if normalized == 'status':
            document.status = normalize(value)
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


def valid_date(value: str) -> bool:
    """Require a complete ISO date that exists in the calendar."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


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
            name = normalize(field_match.group(1))
            buffer = [field_match.group(3)]
            if current is not None and (
                name == 'resposta' or name.startswith('resposta ')
            ):
                stamp = re.search(
                    r'\(([^()]*)\)',
                    field_match.group(1) + field_match.group(2),
                )
                current.answered_on = stamp.group(1).strip() if stamp else ''
            continue
        if buffer and content.startswith((' ', '\t')):
            buffer.append(content)
    _flush_field(current, name, buffer)


def _parse_score(document: Document) -> None:
    section = document.sections.get('placar')
    if section is None:
        return
    rows = table_rows(section.body)
    if len(rows) < 2:
        return
    header_line, header = rows[0]
    _, values = rows[1]
    document.score_line = header_line
    for index, label in enumerate(header):
        state = SCORE_COLUMNS.get(normalize(label))
        if state is None or index >= len(values):
            continue
        raw = values[index].strip()
        if raw.isdigit():
            document.score[state] = int(raw)


def _parse_facts(document: Document) -> None:
    section = document.sections.get('fatos')
    if section is None:
        return
    for number, cells in table_rows(section.body):
        if len(cells) < 3 or not FACT_ID_RE.match(cells[0]):
            continue
        document.facts.append((number, cells[0], cells[-1]))


def parse_document(path: Path) -> Document:
    """Read the current document schema without validating it."""
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


@dataclass(frozen=True)
class Unit:
    """One declared work unit from the handoff decomposition table."""

    name: str
    line: int
    owned: tuple[str, ...]
    objective: str
    acceptance: str
    rollout: str
    rollback: str
    dependencies: tuple[str, ...]
    cells: tuple[str, ...]


def subsection_body(
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
            inside = normalize(match.group(1)) == wanted
            continue
        if inside:
            body.append((number, content))
    return body
