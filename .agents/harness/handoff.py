"""Deterministic readiness gate for spec-driven OpenSpec changes.

The gate has four deliberately separate contracts:

* ``artifact`` validates only the artifact produced by one ``opsx:continue``;
* ``bundle`` validates the complete apply-ready documentation set;
* ``apply`` proves implementation and state-bound mechanical evidence;
* ``completion`` repeats ``bundle`` and proves implementation completion.

Repository-specific values live in ``openspec/handoff.json``.  Unsupported
schemas, invalid configuration and unresolved explicit targets are errors;
the gate never turns those conditions into an empty successful run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness.paths import HARNESS_ROOT, repo_root

REPO_ROOT = repo_root()
CHANGES_ROOT = REPO_ROOT / 'openspec' / 'changes'
CONFIG_PATH = REPO_ROOT / 'openspec' / 'handoff.json'
NON_CHANGE_DIRS = {'archive', 'paused'}
SUPPORTED_SCHEMA = 'spec-driven'
ERROR = 'error'

DEFAULT_TEST_ROOTS = ('tests/', 'test/', 'spec/', '__tests__/')
DEFAULT_SOURCE_ROOTS = (
    'src',
    'lib',
    'app',
    'pkg',
    'internal',
    'tests',
    'test',
    'docs',
    'scripts',
    'dashboard',
    'openspec',
    '.agents',
    '.github',
)


def load_config() -> tuple[dict[str, object], str | None]:
    if not CONFIG_PATH.is_file():
        return {}, None
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f'{CONFIG_PATH.relative_to(REPO_ROOT)}: {exc}'
    if not isinstance(value, dict):
        return {}, 'openspec/handoff.json must contain a JSON object'
    return value, None


CONFIG, CONFIG_ERROR = load_config()


def _config_list(key: str) -> tuple[str, ...]:
    value = CONFIG.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        return ()
    return tuple(value)


TEST_ROOTS = _config_list('testRoots') or DEFAULT_TEST_ROOTS
SOURCE_ROOTS = _config_list('sourceRoots') or DEFAULT_SOURCE_ROOTS
VALIDATION_COMMAND = str(CONFIG.get('validationCommand') or '')
EVIDENCE_PATH = str(CONFIG.get('evidencePath') or 'evidence/gate-report.json')
EVIDENCE_VERIFIER = str(
    CONFIG.get('evidenceVerifier') or '.agents/scripts/harness_verify.py'
)
DECISION_PREFLIGHT = HARNESS_ROOT / 'harness' / 'opsx.py'
SEMANTIC_EVIDENCE_PATH = 'evidence/verification-report.json'

HEADING_RE = re.compile(r'^(#{2,4})\s+(.+)$')
REQUIREMENT_RE = re.compile(r'^###\s+Requirement:\s*(.+?)\s*$')
SCENARIO_RE = re.compile(r'^####\s+Scenario:\s*(.+?)\s*$')
SCENARIO_KIND_RE = re.compile(
    r'^\[(happy|negative|boundary)\]\s+(.+)$', re.IGNORECASE
)
SCENARIO_NA_RE = re.compile(
    r'^-\s+\[(happy|negative|boundary)\]\s+N/A:\s+(.{10,})$', re.I
)
TASK_RE = re.compile(
    r'^- \[([ xX])\] (\d+)\.(\d+)\s+'
    r'\[(prerequisite|implementation|test|validation)\]\s+(.+)$',
    re.I,
)
GROUP_RE = re.compile(r'^##\s+(\d+)\.\s+(.+)$')
TASK_ID_RE = re.compile(r'\b\d+\.\d+\b')
FENCE_RE = re.compile(r'^\s*```')
INLINE_CODE_RE = re.compile(r'`[^`]*`')
PATH_RE = re.compile(
    r'(?:' + '|'.join(re.escape(root) for root in SOURCE_ROOTS) + r')'
    r'/[A-Za-z0-9_.\-/]+(?:\.[A-Za-z0-9_-]+)?'
)
BARE_FILENAME_RE = re.compile(
    r'^[\w-]+\.(?:py|md|toml|ya?ml|json|sh|cfg|ini|txt)$'
)
COMMAND_RE = re.compile(
    r'`\s*(?:npm|uv|bash|sh|python3|pytest|git|openspec|make)\b[^`]*`'
)
PLACEHOLDER_RE = re.compile(
    r'\b(?:TBD|TODO|FIXME|XXX)\b|\?\?\?|<preencher>|<placeholder>|'
    r'\ba definir\b|\bdecidir depois\b|\bto be (?:defined|decided)\b|'
    r'\bdecide during implementation\b',
    re.I,
)
ACRONYM_RE = re.compile(r'\b[A-Z][A-Z0-9]{1,}(?:_[A-Z0-9]+)*\b')
BASE_ACRONYM_STOPLIST = frozenset(
    {
        'ADR',
        'API',
        'AS',
        'BUT',
        'CI',
        'CLI',
        'CPU',
        'CSV',
        'DRY',
        'E2E',
        'ELSE',
        'GIVEN',
        'HTML',
        'HTTP',
        'HTTPS',
        'ID',
        'IF',
        'IO',
        'JSON',
        'MAY',
        'MB',
        'MUST',
        'N/A',
        'NO',
        'NOT',
        'OK',
        'OPSX',
        'OR',
        'QA',
        'RAM',
        'README',
        'REST',
        'SDK',
        'SHALL',
        'SHOULD',
        'SQL',
        'TDD',
        'THEN',
        'UI',
        'URI',
        'URL',
        'UTC',
        'UUID',
        'UX',
        'WHEN',
        'XML',
        'YAML',
    }
)
ACRONYM_STOPLIST = BASE_ACRONYM_STOPLIST | frozenset(
    _config_list('glossaryStoplist')
)
GLOSSARY_HEADING_RE = re.compile(r'^##\s+Glossary\s*$', re.I)
OPEN_QUESTIONS_RE = re.compile(r'^##\s+Open Questions\s*$', re.I)
DECISIONS_RE = re.compile(r'^##\s+Decisions\s*$', re.I)
TRACEABILITY_RE = re.compile(r'^##\s+0\.\s+Traceability\s*$', re.I)
DECISION_RE = re.compile(r'^###\s+D\d+[:.]\s+(.+)$', re.I)
REJECTED_RE = re.compile(
    r'\b(?:rejected|alternative|instead of|considered)\b', re.I
)
DELETION_ACTION_RE = re.compile(
    r'^(?:(?:in\s+[^,\n]+,\s*)?(?:first\s+)?)(?:delete|remove|drop|retire|excluir|remover|apagar)\b',
    re.I,
)


@dataclass(frozen=True)
class Finding:
    level: str
    change: str
    location: str
    code: str
    message: str


@dataclass
class ChangeDocs:
    name: str
    root: Path
    proposal: str
    design: str
    tasks: str
    specs: dict[Path, str]

    @property
    def exempt_reason(self) -> str | None:
        exemptions = CONFIG.get('legacyExemptions', {})
        if not isinstance(exemptions, dict):
            return None
        entry = exemptions.get(self.name)
        if not isinstance(entry, dict):
            return None
        reason = entry.get('reason')
        remove_when = entry.get('removeWhen')
        if not all(
            isinstance(item, str) and item.strip()
            for item in (reason, remove_when)
        ):
            return None
        return f'{reason} Removal trigger: {remove_when}'


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: str
    body: str
    line: int


@dataclass(frozen=True)
class Requirement:
    name: str
    body: str
    line: int
    scenarios: tuple[Scenario, ...]
    na_kinds: frozenset[str]
    path: str

    def at(self, line: int | None = None) -> str:
        """Location of this requirement, or of a line inside it."""
        return f'{self.path}:{self.line if line is None else line}'


@dataclass(frozen=True)
class Task:
    task_id: str
    group: int
    done: bool
    kind: str
    body: str
    line: int


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def evidence_exclusions() -> tuple[str, ...]:
    """Report files of every change, never only the one being verified.

    A gate report is derived output, not verified state. Excluding only the
    current change would let each sibling's report mutate the others'
    fingerprint, so no two changes could hold a green completion gate at once.
    """
    exclusions: list[str] = []
    if CHANGES_ROOT.is_dir():
        for change_dir in sorted(CHANGES_ROOT.iterdir()):
            if not change_dir.is_dir():
                continue
            prefix = f'openspec/changes/{change_dir.name}'
            exclusions.append(f'{prefix}/{SEMANTIC_EVIDENCE_PATH}')
            exclusions.append(f'{prefix}/{EVIDENCE_PATH}')
    return tuple(exclusions)


def current_repository_fingerprint(
    *, exclude_paths: tuple[str, ...] = ()
) -> dict[str, object]:
    """Hash the current Git state and bytes of every changed repository path."""
    head_result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if head_result.returncode != 0 or not head_result.stdout.strip():
        raise ValueError('unable to resolve Git HEAD for semantic evidence')
    status_command = [
        'git',
        'status',
        '--porcelain=v1',
        '--untracked-files=all',
        '-z',
    ]
    status_result = subprocess.run(
        status_command,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if status_result.returncode != 0:
        raise ValueError(
            'unable to resolve changed paths for semantic evidence'
        )
    excluded = {Path(item).as_posix() for item in exclude_paths}
    changed: set[str] = set()
    for raw_entry in status_result.stdout.split(b'\0'):
        if not raw_entry:
            continue
        entry = raw_entry.decode('utf-8', errors='surrogateescape')
        raw_path = entry[3:] if len(entry) >= 3 else entry
        if ' -> ' in raw_path:
            raw_path = raw_path.split(' -> ', 1)[1]
        normalized = Path(raw_path).as_posix()
        if normalized not in excluded:
            changed.add(normalized)

    files: list[dict[str, str]] = []
    for relative in sorted(changed):
        path = REPO_ROOT / relative
        if path.is_file():
            kind = 'file'
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_symlink():
            kind = 'symlink'
            digest = hashlib.sha256(
                path.readlink().as_posix().encode()
            ).hexdigest()
        else:
            kind = 'missing'
            digest = ''
        files.append({'path': relative, 'kind': kind, 'sha256': digest})
    payload = {'head': head_result.stdout.strip(), 'files': files}
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    return {
        'algorithm': 'sha256',
        'value': hashlib.sha256(encoded).hexdigest(),
        'head': payload['head'],
        'changedFiles': [item['path'] for item in files],
    }


def load_change(root: Path) -> ChangeDocs:
    return ChangeDocs(
        name=root.name,
        root=root,
        proposal=read_text(root / 'proposal.md'),
        design=read_text(root / 'design.md'),
        tasks=read_text(root / 'tasks.md'),
        specs={
            path: read_text(path)
            for path in sorted(root.glob('specs/*/spec.md'))
        },
    )


def strip_fences(text: str) -> str:
    output: list[str] = []
    inside = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            inside = not inside
            output.append('')
        else:
            output.append('' if inside else line)
    return '\n'.join(output)


def section_body(text: str, pattern: re.Pattern[str]) -> str | None:
    lines = text.splitlines()
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        if start is None and pattern.match(line):
            start = index + 1
            level = len(line) - len(line.lstrip('#'))
            continue
        match = HEADING_RE.match(line)
        if start is not None and match and len(match.group(1)) <= level:
            return '\n'.join(lines[start:index])
    return None if start is None else '\n'.join(lines[start:])


def parse_tasks(text: str) -> tuple[list[Task], list[int]]:
    tasks: list[Task] = []
    groups: list[int] = []
    current: Task | None = None
    continuation: list[str] = []

    def flush() -> None:
        nonlocal current, continuation
        if current:
            tasks.append(
                Task(
                    current.task_id,
                    current.group,
                    current.done,
                    current.kind,
                    ' '.join([current.body, *continuation]).strip(),
                    current.line,
                )
            )
        current, continuation = None, []

    for number, raw in enumerate(text.splitlines(), 1):
        if match := GROUP_RE.match(raw):
            flush()
            groups.append(int(match.group(1)))
        elif match := TASK_RE.match(raw):
            flush()
            current = Task(
                f'{match.group(2)}.{match.group(3)}',
                int(match.group(2)),
                match.group(1).lower() == 'x',
                match.group(4).lower(),
                match.group(5).strip(),
                number,
            )
        elif current and raw.startswith(('  ', '\t')) and raw.strip():
            continuation.append(raw.strip())
        elif raw.strip():
            flush()
    flush()
    return tasks, groups


def parse_requirements(docs: ChangeDocs) -> list[Requirement]:
    result: list[Requirement] = []
    for path, text in docs.specs.items():
        relative = str(path.relative_to(docs.root))
        lines = text.splitlines()
        starts = [
            (index, match.group(1))
            for index, line in enumerate(lines)
            if (match := REQUIREMENT_RE.match(line))
        ]
        for position, (start, name) in enumerate(starts):
            end = (
                starts[position + 1][0]
                if position + 1 < len(starts)
                else len(lines)
            )
            body_lines = lines[start + 1 : end]
            scenario_starts = [
                (index, match.group(1))
                for index, line in enumerate(body_lines)
                if (match := SCENARIO_RE.match(line))
            ]
            scenarios: list[Scenario] = []
            for scenario_pos, (scenario_start, scenario_name) in enumerate(
                scenario_starts
            ):
                scenario_end = (
                    scenario_starts[scenario_pos + 1][0]
                    if scenario_pos + 1 < len(scenario_starts)
                    else len(body_lines)
                )
                kind_match = SCENARIO_KIND_RE.match(scenario_name)
                kind = kind_match.group(1).lower() if kind_match else ''
                scenarios.append(
                    Scenario(
                        scenario_name,
                        kind,
                        '\n'.join(
                            body_lines[scenario_start + 1 : scenario_end]
                        ),
                        start + scenario_start + 2,
                    )
                )
            result.append(
                Requirement(
                    name,
                    '\n'.join(body_lines),
                    start + 1,
                    tuple(scenarios),
                    frozenset(
                        match.group(1).lower()
                        for line in body_lines
                        if (match := SCENARIO_NA_RE.match(line))
                    ),
                    relative,
                )
            )
    return result


def cited_paths(body: str) -> list[str]:
    return list(dict.fromkeys(PATH_RE.findall(body)))


def validation_command(docs: ChangeDocs) -> str:
    return VALIDATION_COMMAND.replace('<change>', docs.name)


def _finding(
    docs: ChangeDocs,
    location: str,
    code: str,
    message: str,
    level: str = ERROR,
) -> Finding:
    return Finding(level, docs.name, location, code, message)


def check_schema(docs: ChangeDocs) -> list[Finding]:
    schema_file = docs.root / '.openspec.yaml'
    text = read_text(schema_file) or read_text(
        REPO_ROOT / 'openspec' / 'config.yaml'
    )
    match = re.search(r'^schema:\s*([^\s#]+)', text, re.M)
    schema = match.group(1) if match else ''
    if schema == SUPPORTED_SCHEMA:
        return []
    return [
        _finding(
            docs,
            '.openspec.yaml',
            'unsupported-schema',
            f'Expected schema {SUPPORTED_SCHEMA!r}; found {schema or "none"!r}.',
        )
    ]


def check_decision_source(docs: ChangeDocs) -> list[Finding]:
    """Bind active changes to the repo-native provenance preflight."""
    try:
        docs.root.resolve().relative_to(CHANGES_ROOT.resolve())
    except ValueError:
        # Unit fixtures and artifact-isolated checks intentionally live outside
        # the active change tree; their structural contract is tested locally.
        return []
    if not DECISION_PREFLIGHT.is_file():
        return [
            _finding(
                docs,
                'openspec/.agents',
                'decision-preflight-missing',
                'Decision-source preflight script is missing.',
            )
        ]
    # Run as a module with the harness on PYTHONPATH: the preflight is a
    # package module now, so executing its file directly would leave its
    # own package unimportable.
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            f'{DECISION_PREFLIGHT.parent.name}.{DECISION_PREFLIGHT.stem}',
            'preflight',
            '--change',
            docs.name,
            '--json',
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            'PYTHONPATH': str(DECISION_PREFLIGHT.parent.parent),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        detail = result.stderr.strip() or result.stdout.strip()
        return [
            _finding(
                docs,
                '.openspec.yaml',
                'decision-preflight-failed',
                detail or 'Decision-source preflight failed.',
            )
        ]
    findings = payload.get('findings', [])
    if not isinstance(findings, list):
        findings = []
    return [
        _finding(
            docs,
            '.openspec.yaml',
            str(item.get('code', 'decision-preflight-failed')),
            str(item.get('message', 'Decision-source preflight failed.')),
        )
        for item in findings
        if isinstance(item, dict)
    ]


def check_required_artifacts(docs: ChangeDocs) -> list[Finding]:
    findings = [
        _finding(
            docs, name, 'artifact-missing', f'{name} is missing or empty.'
        )
        for name, value in (
            ('proposal.md', docs.proposal),
            ('design.md', docs.design),
            ('tasks.md', docs.tasks),
        )
        if not value.strip()
    ]
    if not docs.specs:
        findings.append(
            _finding(
                docs,
                'specs/',
                'artifact-missing',
                'No delta spec exists at specs/<capability>/spec.md.',
            )
        )
    return findings


def check_placeholders(
    docs: ChangeDocs, artifact: str | None = None
) -> list[Finding]:
    targets: dict[str, str] = {}
    if artifact in (None, 'proposal'):
        targets['proposal.md'] = docs.proposal
    if artifact in (None, 'design'):
        targets['design.md'] = docs.design
    if artifact in (None, 'tasks'):
        targets['tasks.md'] = docs.tasks
    if artifact in (None, 'specs'):
        targets.update(
            (str(path.relative_to(docs.root)), text)
            for path, text in docs.specs.items()
        )
    findings: list[Finding] = []
    for location, text in targets.items():
        for number, line in enumerate(strip_fences(text).splitlines(), 1):
            if match := PLACEHOLDER_RE.search(line):
                findings.append(
                    _finding(
                        docs,
                        f'{location}:{number}',
                        'placeholder',
                        f'Unresolved placeholder {match.group(0)!r}.',
                    )
                )
    return findings


def check_proposal(docs: ChangeDocs) -> list[Finding]:
    if not docs.proposal.strip():
        return [
            _finding(
                docs,
                'proposal.md',
                'artifact-missing',
                'proposal.md is missing or empty.',
            )
        ]
    findings: list[Finding] = []
    sections = {
        'Why': re.compile(r'^##\s+Why\s*$', re.I),
        'What Changes': re.compile(r'^##\s+What Changes\s*$', re.I),
        'Non-Goals': re.compile(r'^##\s+Non-Goals\s*$', re.I),
        'Impact': re.compile(r'^##\s+Impact\s*$', re.I),
    }
    for label, pattern in sections.items():
        body = section_body(docs.proposal, pattern)
        if body is None or not body.strip():
            findings.append(
                _finding(
                    docs,
                    'proposal.md',
                    'proposal-section-empty',
                    f'Section "## {label}" is missing or empty.',
                )
            )
    impact = section_body(docs.proposal, sections['Impact']) or ''
    if not cited_paths(impact):
        findings.append(
            _finding(
                docs,
                'proposal.md',
                'impact-no-path',
                'Impact must cite at least one concrete repository path.',
            )
        )
    return findings


def check_specs(docs: ChangeDocs) -> list[Finding]:
    if not docs.specs:
        return [
            _finding(
                docs, 'specs/', 'artifact-missing', 'No delta spec exists.'
            )
        ]
    findings: list[Finding] = []
    requirements = parse_requirements(docs)
    if not requirements:
        return [
            _finding(
                docs,
                'specs/',
                'spec-empty',
                'No "### Requirement:" was found.',
            )
        ]
    required_kinds = {'happy', 'negative', 'boundary'}
    for requirement in requirements:
        location = requirement.at()
        if not re.search(r'\b(?:SHALL|MUST)\b', requirement.name):
            findings.append(
                _finding(
                    docs,
                    location,
                    'requirement-not-normative',
                    f'Requirement heading {requirement.name!r} must use SHALL or MUST.',
                )
            )
        if not requirement.scenarios:
            findings.append(
                _finding(
                    docs,
                    location,
                    'scenario-missing',
                    f'Requirement {requirement.name!r} has no scenario.',
                )
            )
        present_kinds: set[str] = set()
        for scenario in requirement.scenarios:
            if not scenario.kind:
                findings.append(
                    _finding(
                        docs,
                        requirement.at(scenario.line),
                        'scenario-kind-missing',
                        f'Scenario {scenario.name!r} must start with [happy], [negative], or [boundary].',
                    )
                )
            else:
                present_kinds.add(scenario.kind)
            upper = scenario.body.upper()
            if 'WHEN' not in upper or 'THEN' not in upper:
                findings.append(
                    _finding(
                        docs,
                        requirement.at(scenario.line),
                        'scenario-not-testable',
                        f'Scenario {scenario.name!r} must contain its own WHEN and THEN.',
                    )
                )
        missing = required_kinds - present_kinds - set(requirement.na_kinds)
        findings.extend(
            _finding(
                docs,
                location,
                'scenario-class-missing',
                f'Requirement {requirement.name!r} lacks [{kind}] coverage or a structured N/A rationale.',
            )
            for kind in sorted(missing)
        )
    return findings


def _decision_blocks(text: str) -> list[tuple[str, str, int]]:
    lines = text.splitlines()
    starts = [
        (i, m.group(1))
        for i, line in enumerate(lines)
        if (m := DECISION_RE.match(line))
    ]
    return [
        (
            name,
            '\n'.join(
                lines[
                    start + 1 : starts[pos + 1][0]
                    if pos + 1 < len(starts)
                    else len(lines)
                ]
            ),
            start + 1,
        )
        for pos, (start, name) in enumerate(starts)
    ]


def check_design(docs: ChangeDocs) -> list[Finding]:
    if not docs.design.strip():
        return [
            _finding(
                docs,
                'design.md',
                'artifact-missing',
                'design.md is missing or empty.',
            )
        ]
    findings: list[Finding] = []
    glossary = section_body(docs.design, GLOSSARY_HEADING_RE)
    if glossary is None or not glossary.strip():
        findings.append(
            _finding(
                docs,
                'design.md',
                'glossary-missing',
                'A non-empty "## Glossary" section is required.',
            )
        )
    decisions = _decision_blocks(section_body(docs.design, DECISIONS_RE) or '')
    if not decisions:
        findings.append(
            _finding(
                docs,
                'design.md',
                'decisions-missing',
                'Each design decision must have a "### Dn:" heading.',
            )
        )
    for name, body, line in decisions:
        if not REJECTED_RE.search(body):
            findings.append(
                _finding(
                    docs,
                    f'design.md:{line}',
                    'alternatives-missing',
                    f'Decision {name!r} has no rejected alternative.',
                )
            )
        if not cited_paths(body):
            findings.append(
                _finding(
                    docs,
                    f'design.md:{line}',
                    'decision-no-path',
                    f'Decision {name!r} has no concrete repository path.',
                )
            )
    questions = section_body(docs.design, OPEN_QUESTIONS_RE)
    if questions:
        findings.extend(
            _finding(
                docs,
                'design.md',
                'open-question',
                f'Unanswered question: {line.strip()!r}.',
            )
            for line in strip_fences(questions).splitlines()
            if line.strip().endswith('?')
        )
    return findings


def check_glossary_coverage(docs: ChangeDocs) -> list[Finding]:
    glossary = section_body(docs.design, GLOSSARY_HEADING_RE)
    if glossary is None:
        return []
    prose = '\n'.join((docs.proposal, docs.design, docs.tasks))
    prose = INLINE_CODE_RE.sub(' ', strip_fences(prose))
    prose = '\n'.join(
        line for line in prose.splitlines() if not line.startswith('#')
    )
    used = set(ACRONYM_RE.findall(prose))
    defined = set(ACRONYM_RE.findall(glossary))
    missing = sorted(used - defined - ACRONYM_STOPLIST)
    return (
        []
        if not missing
        else [
            _finding(
                docs,
                'design.md',
                'glossary-incomplete',
                'Acronyms absent from Glossary: ' + ', '.join(missing),
            )
        ]
    )


def _path_is_concrete(path: str) -> bool:
    return bool(
        path
        and not any(token in path for token in ('*', '...', '<', '>'))
        and not path.endswith('/')
    )


def _task_findings(
    docs: ChangeDocs,
    task: Task,
    groups: set[int],
    requirements: list[Requirement],
) -> list[Finding]:
    location = f'tasks.md:{task.line}'
    findings: list[Finding] = []
    paths = cited_paths(task.body)
    if task.group not in groups:
        findings.append(
            _finding(
                docs,
                location,
                'task-orphan-group',
                f'Task {task.task_id} has no matching numbered section.',
            )
        )
    inline_targets = re.findall(r'`([^`]*)`', task.body)
    if any(
        BARE_FILENAME_RE.fullmatch(item.strip()) for item in inline_targets
    ):
        findings.append(
            _finding(
                docs,
                location,
                'task-bare-filename',
                f'Task {task.task_id} cites a bare filename instead of a repository path.',
            )
        )
    if any(not _path_is_concrete(path) for path in paths):
        findings.append(
            _finding(
                docs,
                location,
                'task-non-concrete-path',
                f'Task {task.task_id} contains a glob or non-concrete path.',
            )
        )
    if task.kind == 'implementation' and not paths:
        findings.append(
            _finding(
                docs,
                location,
                'implementation-no-path',
                f'Task {task.task_id} needs a concrete repository path.',
            )
        )
    elif task.kind == 'test':
        if not any(
            any(path.startswith(root) for root in TEST_ROOTS) for path in paths
        ):
            findings.append(
                _finding(
                    docs,
                    location,
                    'test-no-path',
                    f'Task {task.task_id} needs a concrete path under a configured test root.',
                )
            )
        scenario_names = [
            scenario.name for req in requirements for scenario in req.scenarios
        ]
        if not any(name in task.body for name in scenario_names):
            findings.append(
                _finding(
                    docs,
                    location,
                    'test-no-scenario',
                    f'Task {task.task_id} must name the scenario(s) it proves.',
                )
            )
    elif task.kind == 'validation':
        command = validation_command(docs)
        expected = f'`{command}`'
        if not command or expected not in task.body:
            findings.append(
                _finding(
                    docs,
                    location,
                    'validation-command',
                    f'Task {task.task_id} must contain exact command {expected}.',
                )
            )
    elif task.kind == 'prerequisite':
        capabilities = {
            path.parent.name for path in docs.root.glob('specs/*/spec.md')
        }
        capabilities |= {
            path.name
            for path in (REPO_ROOT / 'openspec' / 'specs').glob('*')
            if path.is_dir()
        }
        if not any(f'`{name}`' in task.body for name in capabilities):
            findings.append(
                _finding(
                    docs,
                    location,
                    'prerequisite-unresolved',
                    f'Task {task.task_id} must cite a real capability.',
                )
            )
    return findings


def check_tasks(docs: ChangeDocs) -> list[Finding]:
    if not docs.tasks.strip():
        return [
            _finding(
                docs,
                'tasks.md',
                'artifact-missing',
                'tasks.md is missing or empty.',
            )
        ]
    tasks, groups = parse_tasks(docs.tasks)
    if not tasks:
        return [
            _finding(
                docs,
                'tasks.md',
                'tasks-empty',
                'Tasks must use "- [ ] X.Y [type] description".',
            )
        ]
    requirements = parse_requirements(docs)
    findings = [
        item
        for task in tasks
        for item in _task_findings(docs, task, set(groups), requirements)
    ]
    kinds = {task.kind for task in tasks}
    if 'implementation' not in kinds:
        findings.append(
            _finding(
                docs,
                'tasks.md',
                'implementation-missing',
                'At least one [implementation] task is required.',
            )
        )
    if 'test' not in kinds:
        findings.append(
            _finding(
                docs,
                'tasks.md',
                'tests-missing',
                'At least one [test] task is required.',
            )
        )
    if 'validation' not in kinds:
        findings.append(
            _finding(
                docs,
                'tasks.md',
                'validation-missing',
                'A [validation] task is required.',
            )
        )
    return findings


def _trace_rows(text: str) -> list[list[str]]:
    body = section_body(text, TRACEABILITY_RE)
    if body is None:
        return []
    rows: list[list[str]] = []
    for line in body.splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) != 3 or all(set(cell) <= {'-', ':'} for cell in cells):
            continue
        if cells[0].lower() == 'requirement':
            continue
        rows.append(cells)
    return rows


def check_traceability(docs: ChangeDocs) -> list[Finding]:
    requirements = parse_requirements(docs)
    tasks, _ = parse_tasks(docs.tasks)
    rows = _trace_rows(docs.tasks)
    if not rows:
        return [
            _finding(
                docs,
                'tasks.md',
                'traceability-missing',
                'Expected "## 0. Traceability" with Requirement | Scenarios | Tasks.',
            )
        ]
    findings: list[Finding] = []
    task_by_id = {task.task_id: task for task in tasks}
    requirement_by_name = {item.name: item for item in requirements}
    row_by_name = {row[0]: row for row in rows}
    findings = [
        _finding(
            docs,
            'tasks.md',
            'traceability-unknown-requirement',
            f'Traceability cites unknown requirement {row[0]!r}.',
        )
        for row in rows
        if row[0] not in requirement_by_name
    ]
    duplicate_requirements = {
        row[0] for row in rows if sum(item[0] == row[0] for item in rows) > 1
    }
    findings.extend(
        _finding(
            docs,
            'tasks.md',
            'traceability-duplicate-requirement',
            f'Traceability has duplicate rows for {name!r}.',
        )
        for name in sorted(duplicate_requirements)
    )
    for name, requirement in requirement_by_name.items():
        row = row_by_name.get(name)
        if row is None:
            findings.append(
                _finding(
                    docs,
                    'tasks.md',
                    'requirement-untraced',
                    f'Requirement {name!r} has no traceability row.',
                )
            )
            continue
        scenario_cell, task_cell = row[1], row[2]
        actual_scenarios = {
            item.strip() for item in scenario_cell.split(';') if item.strip()
        }
        expected_scenarios = {
            scenario.name for scenario in requirement.scenarios
        }
        findings.extend(
            _finding(
                docs,
                'tasks.md',
                'scenario-untraced',
                f'Scenario {scenario.name!r} is absent from its traceability row.',
            )
            for scenario in requirement.scenarios
            if scenario.name not in actual_scenarios
        )
        findings.extend(
            _finding(
                docs,
                'tasks.md',
                'traceability-unknown-scenario',
                f'Traceability cites unknown scenario {scenario!r}.',
            )
            for scenario in sorted(actual_scenarios - expected_scenarios)
        )
        ids = TASK_ID_RE.findall(task_cell)
        unknown = [task_id for task_id in ids if task_id not in task_by_id]
        if unknown:
            findings.append(
                _finding(
                    docs,
                    'tasks.md',
                    'traceability-unknown-task',
                    f'Traceability cites unknown task IDs: {", ".join(unknown)}.',
                )
            )
        mapped_kinds = {
            task_by_id[item].kind for item in ids if item in task_by_id
        }
        if not {'implementation', 'test'} <= mapped_kinds:
            findings.append(
                _finding(
                    docs,
                    'tasks.md',
                    'traceability-incomplete',
                    f'Requirement {name!r} must map to [implementation] and [test] tasks.',
                )
            )
    return findings


ARTIFACT_CHECKS: dict[
    str, tuple[Callable[[ChangeDocs], list[Finding]], ...]
] = {
    'proposal': (check_schema, check_proposal),
    'specs': (check_schema, check_specs),
    'design': (check_schema, check_design, check_glossary_coverage),
    'tasks': (check_schema, check_tasks, check_traceability),
}
BUNDLE_CHECKS = (
    check_schema,
    check_decision_source,
    check_required_artifacts,
    check_proposal,
    check_specs,
    check_design,
    check_tasks,
    check_traceability,
    check_glossary_coverage,
)


def check_all_tasks_done(docs: ChangeDocs) -> list[Finding]:
    tasks, _ = parse_tasks(docs.tasks)
    return [
        _finding(
            docs,
            f'tasks.md:{task.line}',
            'task-incomplete',
            f'Task {task.task_id} is still open.',
        )
        for task in tasks
        if not task.done
    ]


def _path_in_git(path: str) -> bool:
    """Check if a path ever existed in Git repository history."""
    result = subprocess.run(
        ['git', 'log', '-1', '--format=%H', '--', path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _is_illustrative_path(body: str, path: str) -> bool:
    """Check if a path in task body is cited as a template/illustrative example."""
    if '/example-' in path or '/example/' in path:
        return True
    body_lower = body.lower()
    for prefix in ('such as', 'for example', 'e.g.'):
        if prefix in body_lower:
            idx = body_lower.find(prefix)
            if path in body[idx:]:
                return True
    return False


def check_completed_paths_exist(docs: ChangeDocs) -> list[Finding]:
    findings: list[Finding] = []
    tasks, _ = parse_tasks(docs.tasks)
    for task in tasks:
        if not task.done or task.kind not in {'implementation', 'test'}:
            continue
        paths = cited_paths(task.body)
        deleting = task.kind == 'implementation' and bool(
            DELETION_ACTION_RE.search(task.body.strip())
        )
        if deleting and len(paths) != 1:
            findings.append(
                _finding(
                    docs,
                    f'tasks.md:{task.line}',
                    'ambiguous-deletion',
                    f'Deletion task {task.task_id} must cite exactly one concrete path.',
                )
            )
            continue
        for path in paths:
            exists = (REPO_ROOT / path).exists() or _path_in_git(path)
            if deleting and (REPO_ROOT / path).exists():
                findings.append(
                    _finding(
                        docs,
                        f'tasks.md:{task.line}',
                        'deletion-incomplete',
                        f'Task {task.task_id} says {path} was deleted, but it still exists.',
                    )
                )
            elif not deleting and not exists:
                if _is_illustrative_path(task.body, path):
                    continue
                findings.append(
                    _finding(
                        docs,
                        f'tasks.md:{task.line}',
                        'phantom-completion',
                        f'Task {task.task_id} is complete but {path} does not exist.',
                    )
                )
    return findings


def check_evidence(docs: ChangeDocs) -> list[Finding]:
    evidence = docs.root / EVIDENCE_PATH
    if not evidence.is_file():
        return [
            _finding(
                docs,
                EVIDENCE_PATH,
                'evidence-missing',
                'Versioned structured gate evidence is missing.',
            )
        ]
    verifier = REPO_ROOT / EVIDENCE_VERIFIER
    if not verifier.is_file():
        return [
            _finding(
                docs,
                EVIDENCE_VERIFIER,
                'evidence-verifier-missing',
                'Configured evidence verifier does not exist.',
            )
        ]
    venv_py = REPO_ROOT / '.venv/bin/python'
    py = str(venv_py) if venv_py.is_file() else sys.executable
    result = subprocess.run(
        [py, str(verifier), '--verify-evidence', str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    detail = (result.stderr or result.stdout).strip().splitlines()
    summary = detail[-1] if detail else f'exit {result.returncode}'
    return [
        _finding(
            docs,
            EVIDENCE_PATH,
            'evidence-invalid',
            f'Structured evidence is not current and green: {summary}',
        )
    ]


def _decision_source_digest(docs: ChangeDocs) -> str | None:
    manifest = read_text(docs.root / '.openspec.yaml')
    match = re.search(
        r'^\s+sha256:\s*([0-9a-f]{64})\s*$', manifest, re.I | re.M
    )
    return match.group(1).lower() if match else None


def _manifest_nested_values(
    docs: ChangeDocs, section_name: str
) -> dict[str, str]:
    """Read scalar values from one two-level manifest section."""
    values: dict[str, str] = {}
    in_section = False
    for raw_line in read_text(docs.root / '.openspec.yaml').splitlines():
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if indent == 0:
            in_section = stripped == f'{section_name}:'
            continue
        if in_section and indent == 2:
            key, separator, value = stripped.partition(':')
            if separator and value.strip():
                values[key] = value.strip().strip('"\'')
    return values


def check_supervised_behavioral_evidence(docs: ChangeDocs) -> list[Finding]:
    """Validate a manifest-declared operator-attested behavioral transcript."""
    values = _manifest_nested_values(docs, 'behavioral_evidence')
    raw_path = values.get('path')
    raw_validator = values.get('validator')
    if raw_path is None and raw_validator is None:
        return []
    if not raw_path or not raw_validator:
        return [
            _finding(
                docs,
                '.openspec.yaml',
                'supervised-transcript-config',
                'behavioral_evidence requires path and validator.',
            )
        ]
    evidence_path = (docs.root / raw_path).resolve()
    validator_path = (REPO_ROOT / raw_validator).resolve()
    try:
        evidence_path.relative_to(docs.root.resolve())
        validator_path.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return [
            _finding(
                docs,
                '.openspec.yaml',
                'supervised-transcript-config',
                'behavioral_evidence paths must remain inside the repository.',
            )
        ]
    if not evidence_path.is_file() or not validator_path.is_file():
        return [
            _finding(
                docs,
                raw_path,
                'supervised-transcript-missing',
                'Declared behavioral evidence or validator is missing.',
            )
        ]
    spec = importlib.util.spec_from_file_location(
        f'supervised_transcript_validator_{id(docs)}', validator_path
    )
    if spec is None or spec.loader is None:
        return [
            _finding(
                docs,
                raw_validator,
                'supervised-transcript-validator',
                'Unable to load the declared behavioral evidence validator.',
            )
        ]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        errors = module.validate_transcript_file(evidence_path, REPO_ROOT)
    except (
        AttributeError,
        ImportError,
        OSError,
        RuntimeError,
        SyntaxError,
    ) as exc:
        return [
            _finding(
                docs,
                raw_validator,
                'supervised-transcript-validator',
                f'Behavioral evidence validator failed: {exc}.',
            )
        ]
    return [
        _finding(
            docs,
            raw_path,
            'supervised-transcript-invalid',
            message,
        )
        for message in errors
    ]


def _evidence_path_resolves(entry: object) -> bool:
    """Resolve a citation and, when present, verify its semantic anchor.

    The optional ``path:line#symbol`` suffix keeps existing file-only and
    line-only reports readable while allowing new reports to prove that the
    cited line names the implementation or test being claimed.
    """
    if not isinstance(entry, str) or not entry.strip():
        return False
    reference = entry.strip()
    line: int | None = None
    anchor: str | None = None
    match = re.fullmatch(
        r'(?P<path>.+?):(?P<line>\d+)'
        r'(?:#(?P<anchor>[A-Za-z_][A-Za-z0-9_]*))?',
        reference,
    )
    if match:
        reference = match.group('path')
        line = int(match.group('line'))
        anchor = match.group('anchor')
    candidate = (REPO_ROOT / reference).resolve()
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    if line is None:
        return candidate.is_file()
    if not candidate.is_file():
        return False
    lines = read_text(candidate).splitlines()
    if not 0 < line <= len(lines):
        return False
    return (
        anchor is None
        or re.search(rf'\b{re.escape(anchor)}\b', lines[line - 1]) is not None
    )


def _evidence_list_resolves(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_evidence_path_resolves(entry) for entry in value)
    )


def _mapping_is_covered(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    status = str(item.get('status', '')).lower()
    evidence = item.get('evidence', [])
    implementation = item.get('implementationEvidence', evidence)
    tests = item.get('testEvidence', evidence)
    return (
        status in {'covered', 'followed', 'passed'}
        and _evidence_list_resolves(implementation)
        and _evidence_list_resolves(tests)
    )


def _semantic_report_metadata_findings(
    docs: ChangeDocs, report: dict[str, object]
) -> list[Finding]:
    required_fields = (
        'schemaVersion',
        'artifactType',
        'changeName',
        'sourceDigest',
        'repositoryFingerprint',
        'requirements',
        'scenarios',
        'designDecisions',
        'blockers',
        'warnings',
        'verdict',
    )
    missing = [field for field in required_fields if field not in report]
    if missing:
        return [
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-shape',
                'Missing semantic report fields: ' + ', '.join(missing) + '.',
            )
        ]
    findings: list[Finding] = []
    if report.get('schemaVersion') != '1.0.0':
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-shape',
                'Unsupported semantic report schemaVersion.',
            )
        )
    if report.get('artifactType') != 'verification-report':
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-shape',
                'Semantic report artifactType must be verification-report.',
            )
        )
    if report.get('changeName') != docs.name:
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-change',
                'Semantic report is bound to a different change.',
            )
        )
    expected_digest = _decision_source_digest(docs)
    source_digest = report.get('sourceDigest')
    if not isinstance(source_digest, str) or (
        expected_digest is not None
        and source_digest.lower() != expected_digest
    ):
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-source',
                'Semantic report sourceDigest does not match .openspec.yaml.',
            )
        )
    fingerprint = report.get('repositoryFingerprint')
    if not isinstance(fingerprint, dict):
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-fingerprint',
                'repositoryFingerprint must be an object.',
            )
        )
    else:
        try:
            current = current_repository_fingerprint(
                exclude_paths=evidence_exclusions()
            )
        except ValueError as exc:
            findings.append(
                _finding(
                    docs,
                    SEMANTIC_EVIDENCE_PATH,
                    'semantic-report-fingerprint',
                    str(exc),
                )
            )
        else:
            if fingerprint != current:
                findings.append(
                    _finding(
                        docs,
                        SEMANTIC_EVIDENCE_PATH,
                        'semantic-report-stale',
                        'repositoryFingerprint does not match current state.',
                    )
                )
    return findings


def _semantic_mapping_findings(
    docs: ChangeDocs,
    expected_names: set[str],
    report_items: object,
    key: str,
    missing_code: str,
    incomplete_code: str,
    subject: str,
) -> list[Finding]:
    items = report_items if isinstance(report_items, list) else []
    names = {str(item.get(key)) for item in items if isinstance(item, dict)}
    findings = [
        _finding(
            docs,
            SEMANTIC_EVIDENCE_PATH,
            missing_code,
            f'{subject} is not mapped: {name}.',
        )
        for name in sorted(expected_names - names)
    ]
    findings.extend(
        _finding(
            docs,
            SEMANTIC_EVIDENCE_PATH,
            incomplete_code,
            f'{subject} mapping is incomplete: {item.get(key)}.',
        )
        for item in items
        if isinstance(item, dict)
        and str(item.get(key)) in expected_names
        and not _mapping_is_covered(item)
    )
    return findings


def _semantic_terminal_findings(
    docs: ChangeDocs, report: dict[str, object]
) -> list[Finding]:
    findings: list[Finding] = []
    blockers = report.get('blockers')
    if not isinstance(blockers, list):
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-shape',
                'blockers must be a list.',
            )
        )
    elif blockers:
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-blocker',
                f'Semantic report contains {len(blockers)} blocker(s).',
            )
        )
    warnings = report.get('warnings')
    if not isinstance(warnings, list):
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-shape',
                'warnings must be a list.',
            )
        )
    else:
        findings.extend(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-warning-scope',
                'Warnings may only classify out-of-contract improvements.',
            )
            for warning in warnings
            if not isinstance(warning, dict)
            or warning.get('classification') != 'out-of-contract'
        )
    if report.get('verdict') != 'passed':
        findings.append(
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-verdict-blocked',
                'Semantic report terminal verdict is not passed.',
            )
        )
    return findings


def check_semantic_evidence(docs: ChangeDocs) -> list[Finding]:
    """Require a current, source-bound semantic verification report."""
    try:
        docs.root.resolve().relative_to(CHANGES_ROOT.resolve())
    except ValueError:
        return []
    report_path = docs.root / SEMANTIC_EVIDENCE_PATH
    if not report_path.is_file():
        return [
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-missing',
                'Structured semantic verification report is missing.',
            )
        ]
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-invalid',
                f'Cannot read semantic verification report: {exc}.',
            )
        ]
    if not isinstance(report, dict):
        return [
            _finding(
                docs,
                SEMANTIC_EVIDENCE_PATH,
                'semantic-report-invalid',
                'Semantic verification report must be a JSON object.',
            )
        ]
    findings = _semantic_report_metadata_findings(docs, report)
    if any(item.code == 'semantic-report-shape' for item in findings):
        return _deduplicate(findings)
    requirements = parse_requirements(docs)
    findings.extend(
        _semantic_mapping_findings(
            docs,
            {item.name for item in requirements},
            report.get('requirements'),
            'requirement',
            'semantic-requirement-unmapped',
            'semantic-requirement-blocker',
            'Requirement',
        )
    )
    findings.extend(
        _semantic_mapping_findings(
            docs,
            {
                scenario.name
                for requirement in requirements
                for scenario in requirement.scenarios
            },
            report.get('scenarios'),
            'scenario',
            'semantic-scenario-unmapped',
            'semantic-scenario-blocker',
            'Scenario',
        )
    )
    findings.extend(
        _semantic_mapping_findings(
            docs,
            {name for name, _, _ in _decision_blocks(docs.design)},
            report.get('designDecisions'),
            'decision',
            'semantic-design-unmapped',
            'semantic-design-blocker',
            'Design decision',
        )
    )
    findings.extend(_semantic_terminal_findings(docs, report))
    return _deduplicate(findings)


def check_delta_sync_state(docs: ChangeDocs) -> list[Finding]:
    """Check the exact operation-aware result owned by ``sync_specs.py``."""
    try:
        docs.root.resolve().relative_to(CHANGES_ROOT.resolve())
    except ValueError:
        return []
    module_path = Path(__file__).resolve().parent / 'sync_specs.py'
    spec = importlib.util.spec_from_file_location(
        'opsx_sync_specs', module_path
    )
    if spec is None or spec.loader is None:
        return [
            _finding(
                docs,
                'specs',
                'sync-check-unavailable',
                f'Unable to load deterministic sync owner: {module_path}.',
            )
        ]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _, issues = module.sync_change(REPO_ROOT, docs.name, write=False)
    return [
        _finding(
            docs,
            f'specs/{issue.capability}/spec.md',
            issue.code,
            issue.message,
        )
        for issue in issues
    ]


APPLY_CHECKS = (
    *BUNDLE_CHECKS,
    check_all_tasks_done,
    check_completed_paths_exist,
    check_evidence,
)


COMPLETION_CHECKS = (
    *APPLY_CHECKS,
    check_semantic_evidence,
    check_supervised_behavioral_evidence,
    check_delta_sync_state,
)


def _artifact_for_path(raw: str) -> str | None:
    path = Path(raw)
    if path.name == 'proposal.md':
        return 'proposal'
    if path.name == 'design.md':
        return 'design'
    if path.name == 'tasks.md':
        return 'tasks'
    if path.name == 'spec.md' and 'specs' in path.parts:
        return 'specs'
    return None


def resolve_targets(raw_targets: list[str]) -> tuple[list[Path], list[str]]:
    resolved: dict[str, Path] = {}
    unresolved: list[str] = []
    for raw in raw_targets:
        candidate = Path(raw)
        absolute = (
            candidate.resolve()
            if candidate.is_absolute()
            else (REPO_ROOT / candidate).resolve()
        )
        change_dir: Path | None = None
        if absolute.is_dir() and absolute.parent == CHANGES_ROOT:
            change_dir = absolute
        else:
            try:
                relative = absolute.relative_to(CHANGES_ROOT)
            except ValueError:
                direct = CHANGES_ROOT / raw
                change_dir = direct if direct.is_dir() else None
            else:
                if relative.parts and relative.parts[0] not in NON_CHANGE_DIRS:
                    possible = CHANGES_ROOT / relative.parts[0]
                    change_dir = possible if possible.is_dir() else None
        if change_dir is None:
            unresolved.append(raw)
        else:
            resolved[change_dir.name] = change_dir
    return [resolved[name] for name in sorted(resolved)], unresolved


def discover_all_changes() -> list[Path]:
    if not CHANGES_ROOT.is_dir():
        return []
    return sorted(
        path
        for path in CHANGES_ROOT.iterdir()
        if path.is_dir() and path.name not in NON_CHANGE_DIRS
    )


def run_checks(
    change_dir: Path, mode: str, artifact: str | None = None
) -> list[Finding]:
    docs = load_change(change_dir)
    if mode == 'artifact':
        if artifact is None:
            raise ValueError('artifact mode requires an artifact identifier')
        checks = ARTIFACT_CHECKS[artifact]
        findings = [item for check in checks for item in check(docs)]
        findings.extend(check_placeholders(docs, artifact))
        return _deduplicate(findings)
    checks = (
        BUNDLE_CHECKS
        if mode == 'bundle'
        else APPLY_CHECKS
        if mode == 'apply'
        else COMPLETION_CHECKS
    )
    findings = [item for check in checks for item in check(docs)]
    findings.extend(check_placeholders(docs))
    return _deduplicate(findings)


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    """Drop only byte-identical repeats.

    The message carries the identity of the offending requirement, scenario
    or task, so it belongs in the key. Leaving it out collapses distinct
    defects that merely share a file and a code, and understates the debt.
    """
    unique: dict[tuple[str, str, str, str], Finding] = {}
    for finding in findings:
        unique.setdefault(
            (finding.level, finding.location, finding.code, finding.message),
            finding,
        )
    return list(unique.values())


def _config_findings(change: str) -> list[Finding]:
    findings: list[Finding] = []
    if CONFIG_ERROR:
        findings.append(
            Finding(
                ERROR,
                change,
                'openspec/handoff.json',
                'config-invalid',
                CONFIG_ERROR,
            )
        )
    findings.extend(
        Finding(
            ERROR,
            change,
            'openspec/handoff.json',
            'config-invalid',
            f'{key} must be a non-empty list of non-empty strings.',
        )
        for key in ('testRoots', 'sourceRoots', 'glossaryStoplist')
        if key in CONFIG and not _config_list(key)
    )
    for key in ('validationCommand', 'evidencePath', 'evidenceVerifier'):
        value = CONFIG.get(key)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                Finding(
                    ERROR,
                    change,
                    'openspec/handoff.json',
                    'config-invalid',
                    f'{key} must be a non-empty string.',
                )
            )
    if isinstance(CONFIG.get('validationCommand'), str) and (
        '<change>' not in VALIDATION_COMMAND
        or '--evidence-path' not in VALIDATION_COMMAND
    ):
        findings.append(
            Finding(
                ERROR,
                change,
                'openspec/handoff.json',
                'config-invalid',
                'validationCommand must produce per-change evidence and '
                'contain both --evidence-path and <change>.',
            )
        )
    if isinstance(CONFIG.get('evidencePath'), str) and EVIDENCE_PATH != (
        'evidence/gate-report.json'
    ):
        findings.append(
            Finding(
                ERROR,
                change,
                'openspec/handoff.json',
                'config-invalid',
                'evidencePath must be evidence/gate-report.json.',
            )
        )
    exemptions = CONFIG.get('legacyExemptions', {})
    if not isinstance(exemptions, dict):
        findings.append(
            Finding(
                ERROR,
                change,
                'openspec/handoff.json',
                'config-invalid',
                'legacyExemptions must be an object.',
            )
        )
    elif any(
        not isinstance(value, dict)
        or not isinstance(value.get('reason'), str)
        or not value.get('reason', '').strip()
        or not isinstance(value.get('removeWhen'), str)
        or not value.get('removeWhen', '').strip()
        for value in exemptions.values()
    ):
        findings.append(
            Finding(
                ERROR,
                change,
                'openspec/handoff.json',
                'config-invalid',
                'Every legacy exemption requires string reason and removeWhen.',
            )
        )
    return findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Validate deterministic OpenSpec handoff readiness.'
    )
    parser.add_argument('targets', nargs='*')
    parser.add_argument(
        '--mode',
        choices=('artifact', 'bundle', 'apply', 'completion'),
        default='bundle',
    )
    parser.add_argument('--artifact', choices=tuple(ARTIFACT_CHECKS))
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--no-exempt', action='store_true')
    parser.add_argument('--json', action='store_true')
    return parser.parse_args(argv)


def _select_change_dirs(args: argparse.Namespace) -> list[Path]:
    if args.all and args.targets:
        raise ValueError('--all cannot be combined with explicit targets')
    change_dirs, unresolved = (
        (discover_all_changes(), [])
        if args.all
        else resolve_targets(args.targets)
    )
    if not args.all and not args.targets:
        raise ValueError('provide a change target or --all')
    if unresolved:
        raise ValueError(
            'unresolved OpenSpec target(s): ' + ', '.join(unresolved)
        )
    return change_dirs


def _infer_artifacts_by_change(targets: list[str]) -> dict[str, set[str]]:
    inferred_artifacts: dict[str, set[str]] = {}
    for raw in targets:
        kind = _artifact_for_path(raw)
        if kind is None:
            continue
        raw_path = Path(raw)
        absolute = (
            raw_path.resolve()
            if raw_path.is_absolute()
            else (REPO_ROOT / raw_path).resolve()
        )
        try:
            name = absolute.relative_to(CHANGES_ROOT).parts[0]
        except (ValueError, IndexError):
            continue
        inferred_artifacts.setdefault(name, set()).add(kind)
    return inferred_artifacts


def _artifact_selection(
    args: argparse.Namespace, change_dirs: list[Path]
) -> dict[str, set[str]]:
    if args.mode != 'artifact':
        return {}
    if args.artifact:
        return {path.name: {args.artifact} for path in change_dirs}
    inferred = _infer_artifacts_by_change(args.targets)
    if any(change_dir.name not in inferred for change_dir in change_dirs):
        raise ValueError(
            'artifact mode requires --artifact for a change name, or '
            'inferable artifact file paths'
        )
    return inferred


def _evaluate_change(
    change_dir: Path, mode: str, artifact_ids: set[str]
) -> list[Finding]:
    findings = _config_findings(change_dir.name)
    if mode != 'artifact':
        findings.extend(run_checks(change_dir, mode))
        return findings
    for artifact_id in sorted(artifact_ids):
        findings.extend(run_checks(change_dir, mode, artifact_id))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        change_dirs = _select_change_dirs(args)
        artifacts_by_change = _artifact_selection(args, change_dirs)
    except ValueError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    results: dict[str, list[Finding]] = {}
    exemptions: dict[str, str] = {}
    failed = False
    for change_dir in change_dirs:
        docs = load_change(change_dir)
        findings = _evaluate_change(
            change_dir,
            args.mode,
            artifacts_by_change.get(docs.name, set()),
        )
        results[docs.name] = findings
        reason = (
            docs.exempt_reason
            if args.mode not in {'apply', 'completion'}
            else None
        )
        if reason and not args.no_exempt:
            exemptions[docs.name] = reason
        elif any(item.level == ERROR for item in findings):
            failed = True

    payload = {
        'mode': args.mode,
        'artifact': args.artifact,
        'exemptions': exemptions,
        'findings': [
            item.__dict__ for findings in results.values() for item in findings
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for change, findings in results.items():
            errors = [item for item in findings if item.level == ERROR]
            status = (
                'EXEMPT'
                if change in exemptions
                else 'FAIL'
                if errors
                else 'OK'
            )
            print(f'{status} {change} [{args.mode}]')
            if change in exemptions:
                print(f'  exemption: {exemptions[change]}')
            for item in findings:
                print(
                    f'  {item.level} {item.location} [{item.code}] {item.message}'
                )
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
