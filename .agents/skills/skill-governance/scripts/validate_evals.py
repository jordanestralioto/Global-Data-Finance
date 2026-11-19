#!/usr/bin/env python3
"""Validate skill trigger and workflow eval sets stored as JSON data.

Each active skill owns `triggers.json` and `evals.json`. With `--evals-root`
they live in `<evals-root>/<skill>/`; without it they live in
`<skills-root>/<skill>/evals/`, the open-standard layout. A positive query
must not reproduce a quoted phrase of the skill description: such a query tests
the description against itself. Exit codes: 0 when every eval set is valid, 1
when findings exist and 2 for invalid usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MIN_PER_SIDE = 3
NO_ROUTE = 'none'
TRIGGERS_FILE = 'triggers.json'
EVALS_FILE = 'evals.json'
TRIGGER_KEYS = frozenset(
    {'query', 'should_trigger', 'routes_to', 'split', 'note'}
)
SPLITS = frozenset({'train', 'validation'})
EVALS_KEYS = frozenset({'skill_name', 'evals', 'runs', 'notes'})
CASE_KEYS = frozenset(
    {'id', 'prompt', 'expected_output', 'files', 'assertions', 'notes'}
)
RUN_KEYS = frozenset({'model', 'status', 'evidence'})
RUN_STATUSES = frozenset({'not run', 'executed'})
FRONTMATTER_RE = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n', re.S)
ARCHIVED_RE = re.compile(r'^status:\s*["\']?archived["\']?\s*$', re.M)
# Matches eval data such as evals.md, EVALS.md, workflow-evals.md,
# eval-scenarios.md or an evals/ folder, but not evaluation-guide.md.
EVAL_NAME_RE = re.compile(
    r'(?:^|[-_])evals?(?:[-_]scenarios)?$|^triggers$', re.I
)
QUOTED_RE = re.compile(r'["“]([^"”\n]+)["”]')
WORD_RE = re.compile(r'\w+(?:-\w+)*')
DESCRIPTION_RE = re.compile(
    r'^description:[ \t]*(?:[>|][-+]?)?(.*(?:\n(?:[ \t].*)?)*)', re.M
)
DESCRIPTION = 'Validate skill trigger and workflow eval sets stored as JSON.'
Phrases = tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class Finding:
    skill: str
    file: str
    message: str


@dataclass
class Context:
    skill: str
    eval_dir: Path
    routes: frozenset[str]
    findings: list[Finding] = field(default_factory=list)
    phrases: Phrases = ()

    def add(self, file_name: str, message: str) -> None:
        path = (self.eval_dir / file_name).as_posix()
        self.findings.append(Finding(self.skill, path, message))


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_archived(skill_file: Path) -> bool:
    match = FRONTMATTER_RE.match(skill_file.read_text(encoding='utf-8'))
    return bool(match and ARCHIVED_RE.search(match.group(1)))


def _words(text: str) -> tuple[str, ...]:
    decomposed = unicodedata.normalize('NFKD', text.casefold())
    plain = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return tuple(WORD_RE.findall(plain))


def read_description(skill_file: Path) -> str:
    """Return the frontmatter description with YAML line folding undone."""
    text = (
        skill_file.read_text(encoding='utf-8') if skill_file.is_file() else ''
    )
    match = FRONTMATTER_RE.match(text)
    found = DESCRIPTION_RE.search(match.group(1)) if match else None
    value = ' '.join(found.group(1).split()) if found else ''
    quoted = len(value) > 1 and value[0] == value[-1] and value[0] in '\'"'
    return value[1:-1] if quoted else value


def description_phrases(description: str) -> Phrases:
    found = QUOTED_RE.findall(description)
    return tuple((text, words) for text in found if (words := _words(text)))


def _check_copy(ctx: Context, where: str, item: dict[str, Any]) -> None:
    words = _words(str(item['query'])) if item['should_trigger'] else ()
    for phrase, target in ctx.phrases:
        size = len(target)
        spans = {words[i : i + size] for i in range(len(words))}
        if words and target in (spans if size > 1 else {words}):
            ctx.add(
                TRIGGERS_FILE,
                f'{where}: positive copies the description phrase "{phrase}";'
                ' rephrase it as a user would',
            )
            return


def discover_skills(skills_root: Path) -> list[str]:
    return sorted(
        path.parent.name
        for path in skills_root.glob('*/SKILL.md')
        if not is_archived(path)
    )


def discover_routes(
    skills_root: Path, agents_root: Path | None
) -> frozenset[str]:
    routes = {NO_ROUTE, *discover_skills(skills_root)}
    if agents_root is not None and agents_root.is_dir():
        routes.update(
            path.name.removesuffix('.md').removesuffix('.agent')
            for path in agents_root.glob('*.md')
        )
    return frozenset(routes)


def _load(ctx: Context, file_name: str) -> Any:
    path = ctx.eval_dir / file_name
    if not path.is_file():
        ctx.add(file_name, 'file is missing')
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        ctx.add(file_name, f'invalid JSON: {exc}')
        return None


def _check_route(ctx: Context, index: int, item: dict[str, Any]) -> None:
    route = item.get('routes_to')
    where = f'query {index}'
    if item['should_trigger']:
        if route is not None:
            ctx.add(TRIGGERS_FILE, f'{where}: positive must not set routes_to')
        return
    if not _is_text(route):
        ctx.add(
            TRIGGERS_FILE,
            f'{where}: negative needs routes_to (skill, agent or "none")',
        )
    elif route == ctx.skill:
        ctx.add(TRIGGERS_FILE, f'{where}: routes_to points to the skill')
    elif route not in ctx.routes:
        ctx.add(TRIGGERS_FILE, f'{where}: unknown routes_to {route!r}')


def _check_query(
    ctx: Context, index: int, item: object, seen: set[str]
) -> bool | None:
    where = f'query {index}'
    if not isinstance(item, dict):
        ctx.add(TRIGGERS_FILE, f'{where}: entry must be an object')
        return None
    extra = sorted(set(item) - TRIGGER_KEYS)
    if extra:
        ctx.add(TRIGGERS_FILE, f'{where}: unknown keys {extra}')
    query = item.get('query')
    if not _is_text(query):
        ctx.add(TRIGGERS_FILE, f'{where}: query must be non-empty text')
        return None
    if not isinstance(item.get('should_trigger'), bool):
        ctx.add(TRIGGERS_FILE, f'{where}: should_trigger must be a boolean')
        return None
    normalized = ' '.join(str(query).casefold().split())
    if normalized in seen:
        ctx.add(TRIGGERS_FILE, f'{where}: duplicate query')
    seen.add(normalized)
    split = item.get('split')
    if split is not None and not (isinstance(split, str) and split in SPLITS):
        ctx.add(TRIGGERS_FILE, f'{where}: split must be train or validation')
    if 'note' in item and not _is_text(item['note']):
        ctx.add(TRIGGERS_FILE, f'{where}: note must be non-empty text')
    _check_route(ctx, index, item)
    _check_copy(ctx, where, item)
    return bool(item['should_trigger'])


def check_triggers(ctx: Context, data: object) -> None:
    if not isinstance(data, list):
        ctx.add(TRIGGERS_FILE, 'top level must be a list of queries')
        return
    seen: set[str] = set()
    sides = [
        _check_query(ctx, index, item, seen)
        for index, item in enumerate(data, start=1)
    ]
    for label, value in (('positive', True), ('negative', False)):
        count = sides.count(value)
        if count < MIN_PER_SIDE:
            ctx.add(
                TRIGGERS_FILE,
                f'{count} {label} queries; at least {MIN_PER_SIDE} required',
            )


def _check_text_list(
    ctx: Context, where: str, key: str, value: object
) -> bool:
    if not isinstance(value, list) or not all(map(_is_text, value)):
        ctx.add(EVALS_FILE, f'{where}: {key} must be a list of text')
        return False
    return bool(value)


def _check_case(ctx: Context, index: int, case: object, ids: set[str]) -> None:
    where = f'eval {index}'
    if not isinstance(case, dict):
        ctx.add(EVALS_FILE, f'{where}: entry must be an object')
        return
    extra = sorted(set(case) - CASE_KEYS)
    if extra:
        ctx.add(EVALS_FILE, f'{where}: unknown keys {extra}')
    case_id = case.get('id')
    if isinstance(case_id, bool) or not (
        isinstance(case_id, int) or _is_text(case_id)
    ):
        ctx.add(EVALS_FILE, f'{where}: id must be an integer or text')
    elif str(case_id) in ids:
        ctx.add(EVALS_FILE, f'{where}: duplicate id {case_id!r}')
    else:
        ids.add(str(case_id))
    if not _is_text(case.get('prompt')):
        ctx.add(EVALS_FILE, f'{where}: prompt must be non-empty text')
    expected = case.get('expected_output')
    if expected is not None and not _is_text(expected):
        ctx.add(EVALS_FILE, f'{where}: expected_output must be text')
    has_assertions = 'assertions' in case and _check_text_list(
        ctx, where, 'assertions', case['assertions']
    )
    if not _is_text(expected) and not has_assertions:
        ctx.add(EVALS_FILE, f'{where}: needs expected_output or assertions')
    if 'notes' in case:
        _check_text_list(ctx, where, 'notes', case['notes'])
    if 'files' in case and _check_text_list(
        ctx, where, 'files', case['files']
    ):
        for name in case['files']:
            if not (ctx.eval_dir / name).exists():
                ctx.add(EVALS_FILE, f'{where}: missing input file {name}')


def _check_runs(ctx: Context, runs: object) -> None:
    if not isinstance(runs, list):
        ctx.add(EVALS_FILE, 'runs must be a list')
        return
    for index, run in enumerate(runs, start=1):
        where = f'run {index}'
        if not isinstance(run, dict) or set(run) - RUN_KEYS:
            ctx.add(
                EVALS_FILE, f'{where}: allowed keys are {sorted(RUN_KEYS)}'
            )
            continue
        if not _is_text(run.get('model')):
            ctx.add(EVALS_FILE, f'{where}: model must be non-empty text')
        status = run.get('status')
        if not (isinstance(status, str) and status in RUN_STATUSES):
            ctx.add(
                EVALS_FILE, f'{where}: status must be "not run" or "executed"'
            )
        elif status == 'executed' and not _is_text(run.get('evidence')):
            ctx.add(EVALS_FILE, f'{where}: executed run needs evidence')


def check_evals(ctx: Context, data: object) -> None:
    if not isinstance(data, dict):
        ctx.add(EVALS_FILE, 'top level must be an object')
        return
    extra = sorted(set(data) - EVALS_KEYS)
    if extra:
        ctx.add(EVALS_FILE, f'unknown keys {extra}')
    if data.get('skill_name') != ctx.skill:
        ctx.add(EVALS_FILE, f'skill_name must be {ctx.skill!r}')
    cases = data.get('evals')
    if not isinstance(cases, list) or not cases:
        ctx.add(EVALS_FILE, 'evals must be a non-empty list')
    else:
        ids: set[str] = set()
        for index, case in enumerate(cases, start=1):
            _check_case(ctx, index, case, ids)
    if 'runs' in data:
        _check_runs(ctx, data['runs'])
    if 'notes' in data:
        _check_text_list(ctx, 'evals.json', 'notes', data['notes'])


def check_runtime_path(ctx: Context, skill_dir: Path) -> None:
    references = skill_dir / 'references'
    if not references.is_dir():
        return
    for path in sorted(references.rglob('*')):
        if EVAL_NAME_RE.search(path.stem if path.is_file() else path.name):
            ctx.findings.append(
                Finding(
                    ctx.skill,
                    path.as_posix(),
                    'eval data inside references/ is on the runtime path',
                )
            )


def validate_skill(
    skill: str, skill_dir: Path, eval_dir: Path, routes: frozenset[str]
) -> list[Finding]:
    phrases = description_phrases(read_description(skill_dir / 'SKILL.md'))
    ctx = Context(skill, eval_dir, routes, phrases=phrases)
    check_runtime_path(ctx, skill_dir)
    if not eval_dir.is_dir():
        ctx.add('', 'eval directory is missing')
        return ctx.findings
    triggers = _load(ctx, TRIGGERS_FILE)
    if triggers is not None:
        check_triggers(ctx, triggers)
    evals = _load(ctx, EVALS_FILE)
    if evals is not None:
        check_evals(ctx, evals)
    return ctx.findings


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--skills-root', type=Path, required=True)
    parser.add_argument(
        '--evals-root',
        type=Path,
        help='Directory with one eval folder per skill (default: in-skill).',
    )
    parser.add_argument('--agents-root', type=Path)
    parser.add_argument('--skill', action='append', default=[])
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    return parser.parse_args(argv)


def _usage_error(message: str) -> int:
    sys.stderr.write(f'error: {message}\n')
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    skills_root: Path = args.skills_root
    if not skills_root.is_dir():
        return _usage_error(f'skills root not found: {skills_root}')
    if args.evals_root is not None and not args.evals_root.is_dir():
        return _usage_error(f'evals root not found: {args.evals_root}')
    active = discover_skills(skills_root)
    unknown = sorted(set(args.skill) - set(active))
    if unknown:
        return _usage_error(f'unknown or archived skills: {unknown}')
    routes = discover_routes(skills_root, args.agents_root)
    findings: list[Finding] = []
    selected = args.skill or active
    for skill in selected:
        base = args.evals_root or skills_root / skill
        eval_dir = base / skill if args.evals_root else base / 'evals'
        findings.extend(
            validate_skill(skill, skills_root / skill, eval_dir, routes)
        )
    if args.format == 'json':
        payload = {
            'valid': not findings,
            'skills': selected,
            'findings': [asdict(finding) for finding in findings],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write('\n')
    else:
        for finding in findings:
            sys.stdout.write(f'{finding.file}: {finding.message}\n')
        status = 'valid' if not findings else f'{len(findings)} finding(s)'
        sys.stdout.write(f'{len(selected)} eval set(s) checked: {status}\n')
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
