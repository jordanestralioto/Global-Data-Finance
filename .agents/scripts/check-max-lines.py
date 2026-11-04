"""Portable max-lines gate: one dependency-free evaluation of Git-tracked
files with role-based limits (production 400, test 1000, documentation 500),
a strict version-1 `.max-lines.toml` policy, a non-growing
`.max-lines-baseline.json`, and deterministic text or JSON reports.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

LIMITS = {'production': 400, 'test': 1000, 'documentation': 500}
ACTIONS = {
    'production': 'refactor',
    'test': 'split-test',
    'documentation': 'split-document',
}
POLICY_NAME = '.max-lines.toml'
BASELINE_NAME = '.max-lines-baseline.json'
INVENTORY_PATH = 'docs/large-files-inventory.md'
INVENTORY_TITLE = '# Large Files Inventory'
SCANNER_PATH = 'scripts/check-max-lines.py'

SUFFIXES = frozenset(
    [
        '.py',
        '.pyi',
        '.pyw',
        '.js',
        '.jsx',
        '.mjs',
        '.cjs',
        '.ts',
        '.tsx',
        '.mts',
        '.cts',
        '.vue',
        '.svelte',
        '.astro',
        '.html',
        '.htm',
        '.xhtml',
        '.ejs',
        '.erb',
        '.hbs',
        '.handlebars',
        '.mustache',
        '.njk',
        '.nunjucks',
        '.pug',
        '.jade',
        '.liquid',
        '.twig',
        '.jinja',
        '.jinja2',
        '.j2',
        '.c',
        '.h',
        '.cc',
        '.cp',
        '.cpp',
        '.cxx',
        '.c++',
        '.hh',
        '.hpp',
        '.hxx',
        '.m',
        '.mm',
        '.cs',
        '.fs',
        '.fsx',
        '.java',
        '.kt',
        '.kts',
        '.scala',
        '.groovy',
        '.gvy',
        '.go',
        '.rs',
        '.zig',
        '.swift',
        '.dart',
        '.nim',
        '.d',
        '.di',
        '.vala',
        '.vapi',
        '.sh',
        '.bash',
        '.zsh',
        '.fish',
        '.nu',
        '.ps1',
        '.psm1',
        '.bat',
        '.cmd',
        '.rb',
        '.php',
        '.pl',
        '.pm',
        '.raku',
        '.rakumod',
        '.lua',
        '.r',
        '.tcl',
        '.el',
        '.ex',
        '.exs',
        '.erl',
        '.hrl',
        '.clj',
        '.cljs',
        '.cljc',
        '.hs',
        '.lhs',
        '.ml',
        '.mli',
        '.lisp',
        '.lsp',
        '.scm',
        '.ss',
        '.rkt',
        '.jl',
        '.pas',
        '.pp',
        '.adb',
        '.ads',
        '.cob',
        '.cbl',
        '.f',
        '.for',
        '.f90',
        '.f95',
        '.f03',
        '.f08',
        '.asm',
        '.s',
        '.v',
        '.sv',
        '.svh',
        '.sol',
        '.sql',
        '.gql',
        '.graphql',
        '.proto',
        '.thrift',
        '.css',
        '.scss',
        '.sass',
        '.less',
        '.styl',
        '.cmake',
        '.bzl',
        '.bazel',
        '.star',
        '.starlark',
        '.tf',
        '.hcl',
        '.cue',
        '.rego',
    ]
)

EXTENSIONLESS = frozenset(
    [
        'Dockerfile',
        'Containerfile',
        'Makefile',
        'GNUmakefile',
        'Justfile',
        'Rakefile',
        'Gemfile',
        'Vagrantfile',
        'Jenkinsfile',
        'BUILD',
        'BUILD.bazel',
        'WORKSPACE',
        'WORKSPACE.bazel',
        'Tiltfile',
        'Procfile',
        'Brewfile',
        'CMakeLists.txt',
        'meson.build',
        'SConstruct',
        'BUCK',
    ]
)

INTERPRETERS = frozenset(
    [
        'python',
        'python3',
        'pypy',
        'node',
        'nodejs',
        'deno',
        'bun',
        'sh',
        'bash',
        'dash',
        'ksh',
        'zsh',
        'fish',
        'ruby',
        'perl',
        'php',
        'lua',
        'Rscript',
        'pwsh',
        'powershell',
    ]
)

HARD_SKIPS = (
    ('.agents/', 'generated-projection'),
    ('.claude/', 'generated-client-mirror'),
    ('.codex/', 'generated-client-mirror'),
    ('.opencode/', 'generated-client-mirror'),
    ('openspec/', 'openspec'),
    ('tests/fixtures/', 'fixture'),
    ('test/fixtures/', 'fixture'),
    ('vendor/', 'vendored'),
    ('third_party/', 'vendored'),
    ('node_modules/', 'vendored'),
    ('dist/', 'build-output'),
    ('build/', 'build-output'),
    ('coverage/', 'build-output'),
)

RECORD_KEYS = (
    'path',
    'classification',
    'line_count',
    'limit',
    'skip_reason',
    'status',
)

Rule = tuple[str, str, str | None]
Policy = tuple[tuple[str, ...], tuple[Rule, ...], bool]
LEGACY_SELF_HOSTING_RULE: Rule = (
    SCANNER_PATH,
    'skip',
    'self-hosting gate implementation',
)


class ConfigError(Exception):
    """Fatal discovery, command, or policy error (exit code 2)."""


@dataclass
class BaselineEntry:
    path: str
    classification: str
    limit: int
    cap: int
    action: str


@dataclass
class Record:
    path: str
    classification: str
    line_count: int | None
    limit: int | None
    skip_reason: str | None
    status: str
    policy_skip: bool = False


@dataclass
class Outcome:
    records: list[Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    evaluated: dict[str, tuple[str, int]] = field(default_factory=dict)


def git(root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ['git', '-C', str(root), *args], capture_output=True, check=False
    )


def repo_root() -> Path:
    proc = git(Path.cwd(), ['rev-parse', '--show-toplevel'])
    if proc.returncode != 0:
        raise ConfigError('tracked-file discovery requires a Git repository')
    return Path(proc.stdout.decode('utf-8', 'replace').strip())


def tracked_paths(root: Path) -> list[str]:
    proc = git(root, ['ls-files', '-z'])
    if proc.returncode != 0:
        raise ConfigError('tracked-file discovery failed')
    return sorted(
        p.decode('utf-8', 'replace') for p in proc.stdout.split(b'\0') if p
    )


def count_lines(data: bytes) -> int:
    return data.count(b'\n') + (0 if not data or data.endswith(b'\n') else 1)


def shebang_interpreter(data: bytes) -> str | None:
    if not data.startswith(b'#!'):
        return None
    parts = (
        data.split(b'\n', 1)[0][2:].strip().decode('utf-8', 'replace').split()
    )
    if not parts:
        return None
    if parts[0].endswith('/env'):
        rest = parts[1:]
        if rest[:1] == ['-S']:
            rest = ' '.join(rest[1:]).split()
        return rest[0] if rest else None
    return parts[0].rsplit('/', 1)[-1]


def match_glob(pattern: str, path: str) -> bool:
    return _match_segments(pattern.split('/'), path.split('/'))


def _match_segments(patterns: list[str], parts: list[str]) -> bool:
    if not patterns:
        return not parts
    if patterns[0] == '**':
        return any(
            _match_segments(patterns[1:], parts[cut:])
            for cut in range(len(parts) + 1)
        )
    return (
        bool(parts)
        and fnmatchcase(parts[0], patterns[0])
        and _match_segments(patterns[1:], parts[1:])
    )


def hard_skip_reason(path: str) -> str | None:
    if path == INVENTORY_PATH:
        return 'generated-inventory'
    if path.startswith('docs/internal/sabatina/') and path.endswith('.md'):
        return 'sabatina-process-record'
    for prefix, reason in HARD_SKIPS:
        if path.startswith(prefix):
            return reason
    parts = path.split('/')
    if 'evidence' in parts:
        return 'evidence'
    if 'snapshots' in parts:
        return 'snapshot'
    if len(parts) >= 3 and parts[0] == 'skills' and parts[2] == 'references':
        return 'skill-reference'
    return None


def classify(
    root: Path, path: str, policy: Policy
) -> tuple[str, str | None, bytes, bool]:
    try:
        info = (root / path).lstat()
    except OSError:
        return 'skip', 'missing-file', b'', False
    if stat.S_ISLNK(info.st_mode):
        return 'skip', 'symlink-not-dereferenced', b'', False
    if not stat.S_ISREG(info.st_mode):
        return 'skip', 'non-regular-file', b'', False
    try:
        data = (root / path).read_bytes()
    except OSError:
        return 'skip', 'missing-file', b'', False
    if b'\0' in data:
        return 'skip', 'binary-data', data, False
    hard = hard_skip_reason(path)
    if hard is not None:
        return 'skip', hard, data, False
    matches = [(p, c, r) for p, c, r in policy[1] if match_glob(p, path)]
    if len(matches) > 1:
        names = ', '.join(pattern for pattern, _, _ in matches)
        raise ConfigError(f'ambiguous policy rules for {path}: {names}')
    if matches:
        _pattern, cls, reason = matches[0]
        return cls, reason, data, cls == 'skip'
    name = path.split('/')[-1]
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    if (
        any(part in ('tests', 'test') for part in path.split('/'))
        or stem.startswith('test_')
        or stem.endswith('_test')
        or '.test.' in name
        or '.spec.' in name
    ):
        return 'test', None, data, False
    if (path.startswith('docs/') and path.endswith('.md')) or (
        name.startswith('README') and name.endswith('.md')
    ):
        return 'documentation', None, data, False
    lower = path.lower()
    if (
        any(lower.endswith(ext) for ext in (*SUFFIXES, *policy[0]))
        or name in EXTENSIONLESS
    ):
        return 'production', None, data, False
    interpreter = shebang_interpreter(data)
    if interpreter is not None:
        cls = 'production' if interpreter in INTERPRETERS else 'unclassified'
        return cls, None, data, False
    if info.st_mode & 0o111:
        return 'unclassified', None, data, False
    return 'skip', 'unrecognized-non-executable', data, False


def evaluate(
    root: Path,
    policy: Policy,
    baseline: list[BaselineEntry],
    selectors: tuple[str, ...],
) -> Outcome:
    outcome = Outcome()
    paths = tracked_paths(root)
    selectors = _select(paths, selectors)
    entries = {entry.path: entry for entry in baseline}
    tracked = set(paths)
    for path in paths:
        cls, reason, data, policy_skip = classify(root, path, policy)
        if cls == 'skip':
            if path in entries:
                outcome.violations.append(
                    f'baseline entry not enforced: {path}'
                )
            record = Record(
                path, 'skip', None, None, reason, 'skip', policy_skip
            )
        elif cls == 'unclassified':
            outcome.errors.append(f'unclassified executable source: {path}')
            if path in entries:
                outcome.violations.append(
                    f'baseline entry not enforced: {path}'
                )
            record = Record(
                path,
                'unclassified',
                count_lines(data),
                None,
                None,
                'unclassified',
            )
        else:
            count = count_lines(data)
            limit = LIMITS[cls]
            entry = entries.get(path)
            record = _enforced_record(path, cls, count, limit, entry, outcome)
            outcome.evaluated[path] = (cls, count)
        if not selectors or any(_matches(path, item) for item in selectors):
            outcome.records.append(record)
    for path in entries:
        if path not in tracked:
            outcome.violations.append(f'baseline entry not tracked: {path}')
    outcome.records.sort(key=lambda record: record.path)
    return outcome


def _enforced_record(
    path: str,
    cls: str,
    count: int,
    limit: int,
    entry: BaselineEntry | None,
    outcome: Outcome,
) -> Record:
    if entry is None:
        if count > limit:
            outcome.violations.append(
                f'{path} exceeds the {limit}-line {cls} limit'
            )
            return Record(path, cls, count, limit, None, 'violation')
        return Record(path, cls, count, limit, None, 'pass')
    if count <= limit:
        outcome.violations.append(f'stale baseline entry: {path}')
        return Record(path, cls, count, limit, None, 'violation')
    if (
        entry.classification != cls
        or entry.limit != limit
        or entry.action != ACTIONS[cls]
    ):
        outcome.violations.append(f'baseline entry class mismatch: {path}')
        return Record(path, cls, count, limit, None, 'violation')
    if count > entry.cap:
        outcome.violations.append(f'{path} exceeds baseline cap {entry.cap}')
        return Record(path, cls, count, limit, None, 'violation')
    return Record(path, cls, count, limit, None, 'baseline')


def _select(paths: list[str], selectors: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for selector in selectors:
        parts = selector.split('/')
        while parts and parts[0] in ('', '.'):
            if parts[0] == '':
                raise ConfigError(f'invalid selector: {selector}')
            parts.pop(0)
        if '\\' in selector or '..' in parts or '' in parts:
            raise ConfigError(f'invalid selector: {selector}')
        clean = '/'.join(parts)
        if not any(_matches(path, clean) for path in paths):
            raise ConfigError(f'selector matches no tracked path: {selector}')
        normalized.append(clean)
    return tuple(normalized)


def _matches(path: str, selector: str) -> bool:
    return not selector or path == selector or path.startswith(selector + '/')


def _int(value: object, name: str) -> int:
    if type(value) is not int:
        raise ConfigError(f'{name} must be an integer')
    return value


def _artifact_path(root: Path, relative: str) -> Path:
    target = root
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        target /= part
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ConfigError(
                f'cannot inspect artifact {relative}: {exc}'
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise ConfigError(f'artifact path is a symbolic link: {relative}')
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ConfigError(
                f'artifact directory is not a directory: {relative}'
            )
        if index == len(parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise ConfigError(f'artifact is not a regular file: {relative}')
    return target


def _read_artifact(root: Path, relative: str) -> bytes | None:
    path = _artifact_path(root, relative)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        with os.fdopen(os.open(path, flags), 'rb') as artifact:
            return artifact.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f'cannot read artifact {relative}: {exc}') from exc


def _write_artifact(root: Path, relative: str, data: bytes) -> None:
    path = _artifact_path(root, relative)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(
            f'cannot create artifact directory {relative}: {exc}'
        ) from exc
    path = _artifact_path(root, relative)
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    )
    try:
        with os.fdopen(os.open(path, flags, 0o666), 'wb') as artifact:
            artifact.write(data)
    except OSError as exc:
        raise ConfigError(f'cannot write artifact {relative}: {exc}') from exc


def load_policy(root: Path) -> Policy:
    data = _read_artifact(root, POLICY_NAME)
    if data is None:
        return (), (), False
    return _parse_policy_bytes(data)


def _parse_policy_bytes(data: bytes) -> Policy:
    try:
        parsed = tomllib.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f'invalid policy: {exc}') from exc
    for key in set(parsed) - {
        'version',
        'source_extensions',
        'rules',
        'inventory',
    }:
        raise ConfigError(f'policy forbids key {key!r}')
    if _int(parsed.get('version'), 'policy version') != 1:
        raise ConfigError('policy must declare version = 1')
    raw = parsed.get('source_extensions', [])
    if not isinstance(raw, list) or not all(
        isinstance(item, str) for item in raw
    ):
        raise ConfigError('source_extensions must be a list of strings')
    extensions: list[str] = []
    for ext in raw:
        if not ext.startswith('.') or len(ext) < 2 or ext != ext.lower():
            raise ConfigError(f'invalid source extension {ext!r}')
        if ext in extensions:
            raise ConfigError(f'duplicate source extension {ext!r}')
        extensions.append(ext)
    rules = tuple(_parse_rule(item) for item in parsed.get('rules', []))
    inventory = parsed.get('inventory')
    enforce = False
    if inventory is not None:
        if not isinstance(inventory, dict):
            raise ConfigError('inventory must be a table')
        for key in set(inventory) - {'path', 'enforce'}:
            raise ConfigError(f'inventory forbids key {key!r}')
        if inventory.get('path') != INVENTORY_PATH:
            raise ConfigError(f'inventory path must be {INVENTORY_PATH!r}')
        enforce = inventory.get('enforce', False)
        if not isinstance(enforce, bool):
            raise ConfigError('inventory enforce must be a boolean')
    return (
        tuple(extensions),
        rules,
        enforce,
    )


def _parse_rule(value: object) -> Rule:
    if not isinstance(value, dict):
        raise ConfigError('rules must be tables')
    for key in set(value) - {'pattern', 'classification', 'reason'}:
        raise ConfigError(f'rule forbids key {key!r}')
    pattern = value.get('pattern')
    if not isinstance(pattern, str):
        raise ConfigError('rule pattern must be a string')
    if (
        '\\' in pattern
        or pattern.startswith('/')
        or '[' in pattern
        or '{' in pattern
        or '..' in pattern.split('/')
        or '' in pattern.split('/')
    ):
        raise ConfigError(f'invalid policy pattern {pattern!r}')
    cls = value.get('classification')
    if cls not in ('production', 'test', 'documentation', 'skip'):
        raise ConfigError(f'rule for {pattern} has an unknown classification')
    reason = value.get('reason')
    if cls == 'skip':
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(f'skip rule for {pattern} requires a reason')
        return pattern, cls, reason
    if reason is not None:
        raise ConfigError(f'rule for {pattern} must not carry a reason')
    return pattern, cls, None


def parse_baseline(data: bytes) -> list[BaselineEntry]:
    try:
        obj = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f'invalid baseline JSON: {exc}') from exc
    if not isinstance(obj, dict) or set(obj) != {'version', 'entries'}:
        raise ConfigError('baseline must contain only version and entries')
    if _int(obj['version'], 'baseline version') != 1:
        raise ConfigError('baseline must declare version 1')
    raw = obj['entries']
    if not isinstance(raw, list):
        raise ConfigError('baseline entries must be a list')
    entries: list[BaselineEntry] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            'path',
            'classification',
            'limit',
            'cap',
            'action',
        }:
            raise ConfigError(
                'baseline entry must hold path, classification, limit, cap, action'
            )
        path = item['path']
        cls = item['classification']
        if not isinstance(path, str) or cls not in LIMITS:
            raise ConfigError(f'baseline entry {path!r} has an invalid class')
        limit = _int(item['limit'], f'limit for {path}')
        cap = _int(item['cap'], f'cap for {path}')
        if (
            limit != LIMITS[cls]
            or cap <= limit
            or item['action'] != ACTIONS[cls]
        ):
            raise ConfigError(
                f'baseline entry {path!r} has wrong limit, cap, or action'
            )
        entries.append(BaselineEntry(path, cls, limit, cap, ACTIONS[cls]))
    paths = [entry.path for entry in entries]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise ConfigError('baseline entries must be unique and sorted by path')
    return entries


def _commit_at(root: Path, rev: str, *, required: bool = False) -> str | None:
    proc = git(root, ['rev-parse', '--verify', rev + '^{commit}'])
    if proc.returncode:
        if required:
            raise ConfigError(
                f'cannot read required baseline predecessor {rev}'
            )
        return None
    return proc.stdout.decode('ascii', 'replace').strip()


def blob_at(
    root: Path, rev: str, path: str, *, required: bool = False
) -> bytes | None:
    commit = _commit_at(root, rev, required=required)
    if commit is None:
        return None
    listing = git(root, ['ls-tree', '-z', commit, '--', path])
    if listing.returncode:
        raise ConfigError(f'cannot read Git revision {rev}')
    for entry in listing.stdout.split(b'\0'):
        name = (
            entry.rsplit(b'\t', 1)[-1].decode('utf-8', 'replace')
            if entry
            else ''
        )
        if name == path:
            shown = git(root, ['show', commit + ':' + path])
            if shown.returncode:
                raise ConfigError(f'cannot read baseline at revision {rev}')
            return shown.stdout
    return None


def first_parent(root: Path, rev: str) -> str | None:
    commit = _commit_at(root, rev)
    if commit is None:
        return None
    proc = git(root, ['cat-file', '-p', commit])
    if proc.returncode:
        raise ConfigError(f'cannot read Git revision {rev}')
    for line in proc.stdout.splitlines():
        if line.startswith(b'parent '):
            return line[7:].decode('ascii', 'replace')
    return None


def history_commits(root: Path, rev: str | None) -> list[str]:
    args = ['log', '--format=%H', *([rev] if rev else []), '--', BASELINE_NAME]
    proc = git(root, args)
    if proc.returncode:
        raise ConfigError('cannot read Git history for the baseline')
    return proc.stdout.decode('utf-8', 'replace').split()


def validate_baseline(
    root: Path,
    current_bytes: bytes | None,
    policy: Policy,
    evaluated: dict[str, tuple[str, int]],
) -> list[str]:
    worktree = parse_baseline(current_bytes) if current_bytes else []
    current = current_bytes or b''
    parent = first_parent(root, 'HEAD')
    predecessor = blob_at(root, 'HEAD', BASELINE_NAME)
    predecessor_rev = 'HEAD'
    if current == predecessor:
        predecessor_rev = parent or 'HEAD'
        predecessor = (
            blob_at(root, predecessor_rev, BASELINE_NAME, required=True)
            if parent is not None
            else None
        )
    if not current:
        if not predecessor:
            return []
        return [
            f'baseline removal invalid: {entry.path}'
            for entry in parse_baseline(predecessor)
            if evaluated.get(entry.path, (None, 0))[1] > entry.limit
        ]
    if predecessor:
        return _transition_check(
            root,
            worktree,
            parse_baseline(predecessor),
            policy,
            evaluated,
            predecessor_rev,
        )
    if parent is None:
        earlier = []
    else:
        _commit_at(root, parent, required=True)
        earlier = history_commits(root, parent)
    if earlier:
        return ['baseline reintroduced after historical removal']
    return _bootstrap_check(worktree, evaluated)


def _transition_check(
    root: Path,
    worktree: list[BaselineEntry],
    predecessor: list[BaselineEntry],
    policy: Policy,
    evaluated: dict[str, tuple[str, int]],
    predecessor_rev: str,
) -> list[str]:
    violations: list[str] = []
    older = {entry.path: entry for entry in predecessor}
    added = [entry for entry in worktree if entry.path not in older]
    scanner_conversion = _is_self_hosting_conversion(
        root, added, policy, evaluated, predecessor_rev
    )
    for entry in worktree:
        previous = older.get(entry.path)
        if previous is None:
            if not (scanner_conversion and entry.path == SCANNER_PATH):
                violations.append(f'baseline added entry: {entry.path}')
        elif (entry.classification, entry.limit, entry.action) != (
            previous.classification,
            previous.limit,
            previous.action,
        ):
            violations.append(f'baseline changed entry: {entry.path}')
        elif entry.cap > previous.cap:
            violations.append(f'baseline raised cap: {entry.path}')
        elif (
            entry.cap < previous.cap
            and evaluated.get(entry.path, (None, 0))[1] > entry.cap
        ):
            violations.append(f'baseline cap no longer covers: {entry.path}')
    current = {entry.path for entry in worktree}
    violations.extend(
        f'baseline removal invalid: {entry.path}'
        for entry in predecessor
        if entry.path not in current
        and evaluated.get(entry.path, (None, 0))[1] > entry.limit
    )
    return violations


def _is_self_hosting_conversion(
    root: Path,
    added: list[BaselineEntry],
    policy: Policy,
    evaluated: dict[str, tuple[str, int]],
    predecessor_rev: str,
) -> bool:
    if len(added) != 1 or added[0].path != SCANNER_PATH:
        return False
    cls, count = evaluated.get(SCANNER_PATH, ('', 0))
    entry = added[0]
    if (
        cls != 'production'
        or count <= LIMITS[cls]
        or LEGACY_SELF_HOSTING_RULE in policy[1]
        or (
            entry.classification,
            entry.limit,
            entry.cap,
            entry.action,
        )
        != ('production', LIMITS['production'], count, ACTIONS['production'])
    ):
        return False
    historical = blob_at(root, predecessor_rev, POLICY_NAME)
    if historical is None:
        return False
    try:
        rules = _parse_policy_bytes(historical)[1]
    except ConfigError:
        return False
    matching = [rule for rule in rules if match_glob(rule[0], SCANNER_PATH)]
    return matching == [LEGACY_SELF_HOSTING_RULE]


def _bootstrap_check(
    entries: list[BaselineEntry], evaluated: dict[str, tuple[str, int]]
) -> list[str]:
    violations: list[str] = []
    entry_paths = {entry.path for entry in entries}
    for entry in entries:
        item = evaluated.get(entry.path)
        if item is None or item[1] <= entry.limit:
            violations.append(f'baseline entry not over limit: {entry.path}')
        elif item[1] != entry.cap:
            violations.append(f'baseline cap mismatch: {entry.path}')
    violations.extend(
        f'missing baseline entry: {path}'
        for path, (cls, count) in evaluated.items()
        if count > LIMITS[cls] and path not in entry_paths
    )
    return violations


def render_inventory(
    records: list[Record], entries: dict[str, BaselineEntry]
) -> str:
    lines = [INVENTORY_TITLE]
    _section(
        lines,
        '## Blocking violations',
        [r for r in records if r.status == 'violation'],
        lambda r: (
            f'- `{r.path}` — {r.classification}, {r.line_count}/{r.limit} — action: {ACTIONS[r.classification]}'
        ),
    )
    _section(
        lines,
        '## Baseline debt',
        [r for r in records if r.status == 'baseline'],
        lambda r: (
            f'- `{r.path}` — {r.classification}, {r.line_count}/{r.limit} (cap {entries[r.path].cap}) — action: {ACTIONS[r.classification]}'
        ),
    )
    _section(
        lines,
        '## Explicit policy skips',
        [r for r in records if r.status == 'skip' and r.policy_skip],
        lambda r: f'- `{r.path}` — {r.skip_reason}',
    )
    hard = [r for r in records if r.status == 'skip' and not r.policy_skip]
    reasons: dict[str, int] = {}
    for record in hard:
        key = record.skip_reason or 'unknown'
        reasons[key] = reasons.get(key, 0) + 1
    _section(
        lines,
        '## Hard skips',
        sorted(reasons),
        lambda reason: f'- {reason}: {reasons[reason]}',
    )
    return '\n'.join(lines) + '\n'


def _section[SectionItem](
    lines: list[str],
    heading: str,
    items: Sequence[SectionItem],
    render: Callable[[SectionItem], str],
) -> None:
    lines.append(heading)
    if items:
        lines.extend(render(item) for item in items)
    else:
        lines.append('None')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='check-max-lines')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check-inventory', action='store_true')
    modes.add_argument('--write-inventory', action='store_true')
    modes.add_argument('--write-baseline', action='store_true')
    parser.add_argument('selectors', nargs='*', metavar='PATH')
    args = parser.parse_args(argv)
    try:
        code, outcome = _execute(args)
    except ConfigError as exc:
        code, outcome = 2, Outcome(errors=[str(exc)])
    for message in (*outcome.violations, *outcome.errors):
        print(message, file=sys.stderr)
    report = _report(args.format, outcome, code)
    if report:
        print(report)
    return code


def _execute(args: argparse.Namespace) -> tuple[int, Outcome]:
    root = repo_root()
    policy = load_policy(root)
    raw_selectors = tuple(args.selectors)
    artifact = (
        args.check_inventory or args.write_inventory or args.write_baseline
    )
    if artifact and raw_selectors:
        raise ConfigError(
            f'artifact modes reject positional selectors: {raw_selectors[0]}'
        )
    if args.write_baseline:
        if history_commits(root, None):
            raise ConfigError('a baseline already exists in Git history')
        outcome = evaluate(root, policy, [], ())
        if outcome.errors:
            return 2, outcome
        bootstrap_entries = [
            {
                'path': path,
                'classification': cls,
                'limit': LIMITS[cls],
                'cap': count,
                'action': ACTIONS[cls],
            }
            for path, (cls, count) in outcome.evaluated.items()
            if count > LIMITS[cls]
        ]
        bootstrap_entries.sort(key=lambda entry: str(entry['path']))
        payload = (
            json.dumps(
                {'version': 1, 'entries': bootstrap_entries},
                indent=2,
                ensure_ascii=False,
            )
            + '\n'
        )
        _write_artifact(root, BASELINE_NAME, payload.encode('utf-8'))
        return 0, evaluate(
            root, policy, parse_baseline(payload.encode('utf-8')), ()
        )
    current = _read_artifact(root, BASELINE_NAME)
    baseline = parse_baseline(current) if current else []
    outcome = evaluate(root, policy, baseline, raw_selectors)
    outcome.violations.extend(
        validate_baseline(root, current, policy, outcome.evaluated)
    )
    entries = {entry.path: entry for entry in baseline}
    if args.write_inventory:
        _write_artifact(
            root,
            INVENTORY_PATH,
            render_inventory(outcome.records, entries).encode('utf-8'),
        )
    if args.write_inventory or args.check_inventory or policy[2]:
        expected = render_inventory(outcome.records, entries).encode('utf-8')
        actual = _read_artifact(root, INVENTORY_PATH) or b''
        if actual != expected:
            outcome.violations.append(
                'inventory is stale; regenerate with --write-inventory'
            )
    return (2 if outcome.errors else 1 if outcome.violations else 0), outcome


def _report(fmt: str, outcome: Outcome, code: int) -> str:
    if fmt == 'text':
        rows: list[str] = []
        for record in outcome.records:
            count = (
                '-' if record.line_count is None else str(record.line_count)
            )
            limit = (
                record.limit
                if record.limit is not None
                else record.skip_reason or '-'
            )
            rows.append(
                '\t'.join(
                    (
                        record.status,
                        record.classification,
                        count,
                        str(limit),
                        record.path,
                    )
                )
            )
        return '\n'.join(rows)
    records = [
        {key: getattr(record, key) for key in RECORD_KEYS}
        for record in outcome.records
    ]
    summary = {
        'total': len(outcome.records),
        'pass': sum(r.status == 'pass' for r in outcome.records),
        'baseline': sum(r.status == 'baseline' for r in outcome.records),
        'violation': sum(r.status == 'violation' for r in outcome.records),
        'skip': sum(r.status == 'skip' for r in outcome.records),
        'unclassified': sum(
            r.status == 'unclassified' for r in outcome.records
        ),
        'violations': outcome.violations,
    }
    return json.dumps(
        {
            'schema_version': 1,
            'records': records,
            'summary': summary,
            'errors': outcome.errors,
            'exit_code': code,
        },
        indent=2,
        ensure_ascii=False,
    )


if __name__ == '__main__':
    raise SystemExit(main())
