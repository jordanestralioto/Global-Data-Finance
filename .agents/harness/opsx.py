#!/usr/bin/env python3
"""CLI repo-native do workflow OPSX.

Substitui o binario global `openspec` pelos verbos que os prompts em
`workflows/` realmente consomem, sem depender de runtime externo. O
formato JSON e compativel com o do CLI anterior; o baseline capturado em
`tests/fixtures/opsx_baseline/` e o contrato provado pelos testes.

Subcomandos:
  list          changes ativas, com progresso de tasks.
  status        estado dos artefatos de uma change.
  instructions  instrucao autoral do artefato, com context e rules do projeto.
  new           scaffold de uma change nova.
  validate      formato de requirement/scenario das specs principais.

O schema mora em `openspec/schema/` e pertence a este repositorio.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness import handoff as GATE
from harness import sabatina
from harness.paths import HARNESS_ROOT

REPO_ROOT: Path = GATE.REPO_ROOT
CHANGES_ROOT: Path = GATE.CHANGES_ROOT
NON_CHANGE_DIRS: frozenset[str] = frozenset(GATE.NON_CHANGE_DIRS)
SUPPORTED_SCHEMA: str = GATE.SUPPORTED_SCHEMA

SPECS_ROOT = REPO_ROOT / 'openspec' / 'specs'
# The schema ships with the harness; specs and config belong to the
# repository being operated on.
SCHEMA_ROOT = HARNESS_ROOT / 'openspec' / 'schema'
CONFIG_PATH = REPO_ROOT / 'openspec' / 'config.yaml'

APPLY_ID = 'apply'
CHANGE_NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
CHECKBOX_RE = re.compile(r'^\s*- \[([ xX])\]\s+(.*)$')
WHEN_RE = re.compile(r'\bWHEN\b')
THEN_RE = re.compile(r'\bTHEN\b')
NORMATIVE_RE = re.compile(r'\b(SHALL|MUST)\b')
MISPLACED_SCENARIO_RE = re.compile(r'^###\s+Scenario:', re.I)
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DECISION_ID_RE = re.compile(r'^Q\d+$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$', re.I)
ARCHIVED_CHANGE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}-(.+)$')
SourceNamespace = tuple[str, str, str]
Descriptor = tuple[str, SourceNamespace | None, dict[str, object], list[str]]

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


@dataclass
class SpecRequirement:
    """Um `### Requirement:` com seu texto e seus cenarios."""

    name: str
    preamble: list[str] = field(default_factory=list)
    scenarios: list[tuple[str, list[str]]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Leitor do subconjunto YAML usado por openspec/config.yaml
# ---------------------------------------------------------------------------


def _dedent(lines: list[str]) -> list[str]:
    indents = [len(x) - len(x.lstrip()) for x in lines if x.strip()]
    width = min(indents) if indents else 0
    return [line[width:] if line.strip() else '' for line in lines]


def _fold(lines: list[str]) -> str:
    out: list[str] = []
    for line in _dedent(lines):
        if not line:
            out.append('\n')
        elif out and not out[-1].endswith('\n'):
            out[-1] = f'{out[-1]} {line}'
        else:
            out.append(line)
    return ''.join(out)


def _literal(lines: list[str]) -> str:
    body = '\n'.join(_dedent(lines)).rstrip('\n')
    return f'{body}\n' if body else ''


def _block(lines: list[str], style: str) -> str:
    if style.startswith('|'):
        return _literal(lines)
    folded = _fold(lines)
    return folded if style.endswith('-') else f'{folded}\n'


def _collect_block(
    lines: list[str], start: int, indent: int
) -> tuple[list[str], int]:
    body: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
        index += 1
    while body and not body[-1].strip():
        body.pop()
    return body, index


def _parse_rules(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    rules: dict[str, list[str]] = {}
    index = start
    current: str | None = None
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped and indent == 0:
            break
        if not stripped or stripped.startswith('#'):
            index += 1
            continue
        if indent == 2 and stripped.endswith(':'):
            current = stripped[:-1]
            rules[current] = []
            index += 1
            continue
        if indent == 4 and stripped.startswith('-') and current is not None:
            style = stripped[1:].strip() or '>'
            body, index = _collect_block(lines, index + 1, 4)
            rules[current].append(_block(body, style))
            continue
        index += 1
    return {'rules': rules}, index


def parse_config_yaml(text: str) -> dict[str, Any]:
    """Le o subconjunto YAML que `openspec/config.yaml` usa.

    Cobre escalar simples, bloco `|`/`>`/`>-` no topo e o mapa `rules` com
    listas de blocos. Qualquer outra construcao e ignorada em vez de virar
    dado silenciosamente errado; o teste compara esta saida com PyYAML.
    """
    lines = text.splitlines()
    data: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or line[:1].isspace():
            index += 1
            continue
        key, _, raw = stripped.partition(':')
        value = raw.strip()
        index += 1
        if key == 'rules' and not value:
            nested, index = _parse_rules(lines, index)
            data.update(nested)
        elif value.startswith(('|', '>')):
            body, index = _collect_block(lines, index, 0)
            data[key] = _block(body, value)
        elif value:
            data[key] = value
    return data


def load_authoring_config() -> tuple[str, dict[str, list[str]]]:
    """Devolve o overlay autoral do projeto: `context` e `rules`.

    `parse_config_yaml` preserva o newline final que o bloco `|` do YAML
    carrega; a emissao remove esse newline para manter a saida identica a do
    CLI anterior, que o cortava.
    """
    if not CONFIG_PATH.is_file():
        return '', {}
    data = parse_config_yaml(CONFIG_PATH.read_text(encoding='utf-8'))
    context = data.get('context', '')
    rules = data.get('rules', {})
    return (
        context.rstrip('\n') if isinstance(context, str) else '',
        rules if isinstance(rules, dict) else {},
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def load_schema() -> dict[str, Any]:
    path = SCHEMA_ROOT / f'{SUPPORTED_SCHEMA}.json'
    if not path.is_file():
        raise FileNotFoundError(f'schema ausente: {path}')
    schema: dict[str, Any] = json.loads(path.read_text(encoding='utf-8'))
    return schema


def _artifacts(schema: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = schema.get('artifacts', [])
    return artifacts if isinstance(artifacts, list) else []


def _artifact_by_id(
    schema: dict[str, Any], artifact_id: str
) -> dict[str, Any]:
    for artifact in _artifacts(schema):
        if artifact.get('id') == artifact_id:
            return artifact
    raise KeyError(artifact_id)


def _schema_text(kind: str, name: str) -> str:
    path = SCHEMA_ROOT / kind / name
    if not path.is_file():
        raise FileNotFoundError(f'arquivo de schema ausente: {path}')
    return path.read_text(encoding='utf-8').rstrip('\n')


def ordered_artifacts(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordem topologica, empate resolvido pelo id em ordem alfabetica."""
    pending = {a['id']: set(a.get('requires', [])) for a in _artifacts(schema)}
    by_id = {a['id']: a for a in _artifacts(schema)}
    ordered: list[dict[str, Any]] = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if not deps)
        if not ready:
            raise ValueError('ciclo no grafo de artefatos do schema')
        for name in ready:
            ordered.append(by_id[name])
            del pending[name]
        for deps in pending.values():
            deps.difference_update(ready)
    return ordered


def unlocked_by(schema: dict[str, Any], artifact_id: str) -> list[str]:
    return sorted(
        artifact['id']
        for artifact in _artifacts(schema)
        if artifact_id in artifact.get('requires', [])
    )


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


def iter_change_dirs() -> list[Path]:
    if not CHANGES_ROOT.is_dir():
        return []
    return sorted(
        path
        for path in CHANGES_ROOT.iterdir()
        if path.is_dir() and path.name not in NON_CHANGE_DIRS
    )


def iter_decision_change_dirs() -> list[Path]:
    """Return active and archived decision owners.

    Archive is terminal lifecycle state, not deletion from the ownership
    registry.  Paused changes remain excluded because they are not terminal.
    """
    result = iter_change_dirs()
    archive_root = CHANGES_ROOT / 'archive'
    if archive_root.is_dir():
        result.extend(
            path for path in sorted(archive_root.iterdir()) if path.is_dir()
        )
    return result


def _logical_change_name(change_dir: Path) -> str:
    if change_dir.parent.name != 'archive':
        return change_dir.name
    match = ARCHIVED_CHANGE_RE.fullmatch(change_dir.name)
    return match.group(1) if match else change_dir.name


def resolve_change(name: str) -> Path:
    path = CHANGES_ROOT / name
    if not path.is_dir() or name in NON_CHANGE_DIRS:
        raise FileNotFoundError(f'change nao encontrada: {name}')
    return path


def _manifest_value(raw: str) -> object:
    value = raw.strip()
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [
            item.strip().strip('"\'')
            for item in inner.split(',')
            if item.strip()
        ]
    return value.strip('"\'')


def load_change_manifest(change_dir: Path) -> dict[str, object]:
    """Read the small YAML subset used by a change manifest."""
    path = change_dir / '.openspec.yaml'
    if not path.is_file():
        return {}
    manifest: dict[str, object] = {}
    nested: dict[str, object] | None = None
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith('#'):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        key, separator, raw_value = stripped.partition(':')
        if not separator:
            continue
        if indent == 0:
            if raw_value.strip():
                manifest[key] = _manifest_value(raw_value)
                nested = None
            else:
                nested = {}
                manifest[key] = nested
        elif indent == 2 and nested is not None:
            nested[key] = _manifest_value(raw_value)
    return manifest


def _provenance_finding(code: str, message: str) -> dict[str, str]:
    return {'code': code, 'message': message}


def _unverifiable_owner(change_dir: Path, reason: str) -> dict[str, str]:
    return {
        'code': 'decision-owner-unverifiable',
        'message': f'{_logical_change_name(change_dir)} cannot prove its decision ownership ({reason}).',
    }


def _resolve_source_path(
    raw_path: object, findings: list[dict[str, str]]
) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        findings.append(
            _provenance_finding(
                'decision-source-path',
                'decision_source.path must be a repository-relative path.',
            )
        )
        return None
    candidate = Path(raw_path)
    try:
        resolved = (REPO_ROOT / candidate).resolve()
        resolved.relative_to(REPO_ROOT.resolve())
    except (OSError, ValueError):
        findings.append(
            _provenance_finding(
                'decision-source-path',
                'decision_source.path must remain inside the repository.',
            )
        )
        return None
    if candidate.is_absolute():
        findings.append(
            _provenance_finding(
                'decision-source-path',
                'decision_source.path must be repository-relative.',
            )
        )
    return resolved


def _normalize_decision_ids(
    raw_ids: object, findings: list[dict[str, str]]
) -> list[str]:
    if not isinstance(raw_ids, list) or not raw_ids:
        findings.append(
            _provenance_finding(
                'decision-source-ids',
                'decision_source.decision_ids must be a nonempty list.',
            )
        )
        return []
    normalized = [str(item) for item in raw_ids]
    invalid = [
        item for item in normalized if not DECISION_ID_RE.fullmatch(item)
    ]
    if invalid:
        findings.append(
            _provenance_finding(
                'decision-source-ids',
                'Invalid decision IDs: ' + ', '.join(invalid) + '.',
            )
        )
    if len(set(normalized)) != len(normalized):
        findings.append(
            _provenance_finding(
                'decision-source-ids',
                'decision_source.decision_ids must not contain duplicates.',
            )
        )
    return normalized


def _normalize_dependencies(
    raw_dependencies: object,
    change_dir: Path,
    findings: list[dict[str, str]],
) -> list[str]:
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_dependencies
    ):
        findings.append(
            _provenance_finding(
                'decision-source-dependencies',
                'decision_source.depends_on must be a list of change names.',
            )
        )
        return []
    normalized = [str(item) for item in raw_dependencies]
    if _logical_change_name(change_dir) in normalized:
        findings.append(
            _provenance_finding(
                'decision-source-dependencies',
                'A change cannot depend on itself.',
            )
        )
    return normalized


def _validate_source_file(
    source_type: object,
    source_path: Path | None,
    digest: object,
    decision_ids: list[str],
    findings: list[dict[str, str]],
) -> None:
    if source_path is None:
        return
    if not source_path.is_file():
        findings.append(
            _provenance_finding(
                'decision-source-missing',
                f'Source file does not exist: {source_path.relative_to(REPO_ROOT)}.',
            )
        )
        return
    source_bytes = source_path.read_bytes()
    actual_digest = hashlib.sha256(source_bytes).hexdigest()
    if isinstance(digest, str) and actual_digest != digest.lower():
        findings.append(
            _provenance_finding(
                'decision-source-digest-mismatch',
                f'Expected {digest}, found {actual_digest}.',
            )
        )
    source_text = source_bytes.decode('utf-8', errors='replace')
    missing_ids = [
        decision_id
        for decision_id in decision_ids
        if not re.search(
            rf'(?<![A-Z0-9]){re.escape(decision_id)}(?![A-Z0-9])',
            source_text,
        )
    ]
    findings.extend(
        _provenance_finding(
            'decision-id-not-found',
            f'{decision_id} does not occur in {source_path.relative_to(REPO_ROOT)}.',
        )
        for decision_id in missing_ids
    )
    if source_type == 'sabatina':
        _validate_closed_sabatina(source_path, findings)


def _validate_sabatina_ownership(
    source_path: Path,
    change_name: str,
    decision_ids: list[str],
    findings: list[dict[str, str]],
    dependencies: list[str] | None = None,
) -> None:
    validator = sabatina
    document = validator.parse_document(source_path)
    body = validator._subsection_body(
        document, 'handoff', validator.HANDOFF_ROUTE_SECTION
    )
    table = validator._find_table(validator._tables(body), 'ids')
    units = validator._decomposition_units(table) if table else []
    unit = next((item for item in units if item.name == change_name), None)
    if unit is None:
        findings.append(
            _provenance_finding(
                'decision-owner-not-declared',
                f'{change_name} is absent from the sabatina decomposition.',
            )
        )
        return
    declared = list(unit.owned)
    if declared != decision_ids:
        findings.append(
            _provenance_finding(
                'decision-owner-mismatch',
                f'{change_name} declares {decision_ids}, but the sabatina '
                f'assigns {declared}.',
            )
        )
    if dependencies is not None and list(unit.dependencies) != dependencies:
        findings.append(
            _provenance_finding(
                'decision-dependency-mismatch',
                f'{change_name} declares dependencies {dependencies}, but '
                f'the sabatina assigns {list(unit.dependencies)}.',
            )
        )


def _validate_closed_sabatina(
    source_path: Path, findings: list[dict[str, str]]
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'harness.sabatina',
            '--document',
            str(source_path),
            '--phase',
            'closed',
            '--json',
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stdout.strip() or result.stderr.strip()
        findings.append(
            _provenance_finding(
                'sabatina-not-closed',
                f'Closed sabatina validation failed: {detail[-500:]}.',
            )
        )


def _source_descriptor(
    change_dir: Path,
) -> tuple[
    dict[str, object] | None, SourceNamespace | None, list[dict[str, str]]
]:
    raw_source = load_change_manifest(change_dir).get('decision_source')
    if not isinstance(raw_source, dict):
        missing = _provenance_finding(
            'decision-source-missing',
            'Change must declare a decision_source envelope in .openspec.yaml.',
        )
        return None, None, [missing]
    findings: list[dict[str, str]] = []
    source = dict(raw_source)
    source_type = source.get('type')
    if source_type not in {'sabatina', 'user-contract'}:
        findings.append(
            _provenance_finding(
                'decision-source-type',
                "decision_source.type must be 'sabatina' or 'user-contract'.",
            )
        )
    source_path = _resolve_source_path(source.get('path'), findings)
    digest = source.get('sha256')
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        findings.append(
            _provenance_finding(
                'decision-source-digest',
                'decision_source.sha256 must be a 64-character SHA-256 digest.',
            )
        )
    confirmed = source.get('confirmed_on')
    if not isinstance(confirmed, str) or not DATE_RE.fullmatch(confirmed):
        findings.append(
            _provenance_finding(
                'decision-source-confirmation',
                'decision_source.confirmed_on must use YYYY-MM-DD.',
            )
        )
    decision_ids = _normalize_decision_ids(
        source.get('decision_ids'), findings
    )
    if 'depends_on' not in source:
        findings.append(
            _provenance_finding(
                'decision-source-dependencies-missing',
                'decision_source.depends_on is required; declare [] for a root '
                'change.',
            )
        )
        dependencies = []
    else:
        dependencies = _normalize_dependencies(
            source.get('depends_on'), change_dir, findings
        )
    _validate_source_file(
        source_type, source_path, digest, decision_ids, findings
    )
    if source_type == 'sabatina' and source_path and source_path.is_file():
        _validate_sabatina_ownership(
            source_path,
            _logical_change_name(change_dir),
            decision_ids,
            findings,
            dependencies,
        )
    source['decision_ids'] = decision_ids
    source['depends_on'] = dependencies
    namespace = None
    if (
        source_type in ('sabatina', 'user-contract')
        and source_path is not None
        and isinstance(digest, str)
        and SHA256_RE.fullmatch(digest)
    ):
        namespace = (
            str(source_type),
            source_path.relative_to(REPO_ROOT.resolve()).as_posix(),
            digest.lower(),
        )
    return source, namespace, findings


def _dependency_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> list[str] | None:
        if name in visiting:
            return [*stack[stack.index(name) :], name]
        if name in visited:
            return None
        visiting.add(name)
        stack.append(name)
        for dependency in graph.get(name, []):
            if cycle := visit(dependency):
                return cycle
        stack.pop()
        visiting.remove(name)
        visited.add(name)
        return None

    for name in sorted(graph):
        if cycle := visit(name):
            return cycle
    return None


def _str_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def validate_decision_source(
    change_dir: Path, change_dirs: list[Path] | None = None
) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    """Validate one source envelope and its durable ownership graph."""
    decision_dirs = (
        change_dirs if change_dirs is not None else iter_decision_change_dirs()
    )
    source, source_namespace, findings = _source_descriptor(change_dir)
    descriptors: list[Descriptor] = []
    for candidate in decision_dirs:
        candidate_source, namespace, candidate_findings = _source_descriptor(
            candidate
        )
        if candidate_source is None:
            if 'decision_source' in load_change_manifest(candidate):
                findings.append(
                    _unverifiable_owner(candidate, 'decision-source-missing')
                )
            continue
        if (
            candidate_findings
            and candidate.resolve() != change_dir.resolve()
            and namespace in (None, source_namespace)
        ):
            codes = ', '.join(
                sorted({item['code'] for item in candidate_findings})
            )
            findings.append(_unverifiable_owner(candidate, codes))
        ids = _str_list(candidate_source.get('decision_ids'))
        descriptors.append(
            (_logical_change_name(candidate), namespace, candidate_source, ids)
        )
    if source is not None:
        owners: dict[tuple[tuple[str, str, str], str], list[str]] = {}
        for name, namespace, _descriptor, ids in descriptors:
            if namespace is None:
                continue
            for decision_id in ids:
                owners.setdefault((namespace, decision_id), []).append(name)
        for (_, decision_id), names in sorted(owners.items()):
            # Ownership is exclusive; dependencies never grant co-ownership.
            if len(names) > 1:
                findings.append(
                    _provenance_finding(
                        'decision-id-duplicate-owner',
                        f'{decision_id} is owned by sibling changes:'
                        f' {", ".join(names)}.',
                    )
                )
    graph: dict[str, list[str]] = {}
    known_names = {name for name, _, _, _ in descriptors}
    for name, _, descriptor, _ in descriptors:
        dependencies = _str_list(descriptor.get('depends_on'))
        if unknown := sorted(set(dependencies) - known_names):
            findings.append(
                _provenance_finding(
                    'decision-dependency-unknown',
                    f'{name} depends on unknown changes: {", ".join(unknown)}.',
                )
            )
        graph[name] = [item for item in dependencies if item in known_names]
    cycle = _dependency_cycle(graph)
    if cycle:
        findings.append(
            _provenance_finding(
                'decision-dependency-cycle',
                'Decision-source dependency cycle: '
                + ' -> '.join(cycle)
                + '.',
            )
        )
    return source, findings


def cmd_preflight(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    change_dir = resolve_change(args.change)
    source, findings = validate_decision_source(change_dir)
    return (
        EXIT_FINDINGS if findings else EXIT_OK,
        {
            'changeName': change_dir.name,
            'status': 'error' if findings else 'ok',
            'decisionSource': source,
            'findings': findings,
        },
    )


def cmd_fingerprint(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    change_dir = resolve_change(args.change)
    return EXIT_OK, {
        'changeName': change_dir.name,
        'repositoryFingerprint': GATE.current_repository_fingerprint(
            exclude_paths=GATE.evidence_exclusions()
        ),
    }


def count_tasks(change_dir: Path) -> tuple[int, int]:
    path = change_dir / 'tasks.md'
    if not path.is_file():
        return 0, 0
    total = 0
    complete = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        match = CHECKBOX_RE.match(line)
        if match:
            total += 1
            complete += match.group(1).lower() == 'x'
    return complete, total


def _created_date(change_dir: Path) -> str:
    created = load_change_manifest(change_dir).get('created')
    if isinstance(created, str) and DATE_RE.fullmatch(created):
        return created
    return '0000-00-00'


def artifact_exists(change_dir: Path, generates: str) -> bool:
    if any(token in generates for token in ('*', '?')):
        return any(change_dir.glob(generates))
    return (change_dir / generates).is_file()


def artifact_states(
    change_dir: Path, schema: dict[str, Any]
) -> dict[str, str]:
    done = {
        artifact['id']: artifact_exists(change_dir, artifact['generates'])
        for artifact in _artifacts(schema)
    }
    states: dict[str, str] = {}
    for artifact in _artifacts(schema):
        name = artifact['id']
        if done[name]:
            states[name] = 'done'
        elif all(done.get(dep, False) for dep in artifact.get('requires', [])):
            states[name] = 'ready'
        else:
            states[name] = 'blocked'
    return states


def _apply_context_path(
    change_dir: Path, generates: str
) -> tuple[str | list[str], list[dict[str, str]]]:
    """Resolve one apply context entry and report missing files."""
    if not any(token in generates for token in ('*', '?', '[')):
        path = change_dir / generates
        if path.is_file():
            return str(path), []
        return [], [
            {
                'code': 'apply-context-missing',
                'message': f'Context file does not exist: {path}.',
            }
        ]
    paths = sorted(
        (path for path in change_dir.glob(generates) if path.is_file()),
        key=lambda path: path.relative_to(change_dir).as_posix(),
    )
    if paths:
        return [str(path) for path in paths], []
    return [], [
        {
            'code': 'apply-context-glob-empty',
            'message': f'Context glob does not match any file: {generates}.',
        }
    ]


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------


def cmd_list(_: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for change_dir in iter_change_dirs():
        complete, total = count_tasks(change_dir)
        if total == 0:
            state = 'no-tasks'
        elif complete >= total:
            state = 'complete'
        else:
            state = 'in-progress'
        changes.append(
            {
                'name': change_dir.name,
                'completedTasks': complete,
                'totalTasks': total,
                'lastModified': f'{_created_date(change_dir)}T00:00:00.000Z',
                'status': state,
            }
        )
    changes.sort(key=lambda item: str(item['name']))
    changes.sort(key=lambda item: str(item['lastModified']), reverse=True)
    return EXIT_OK, {'changes': changes}


def cmd_status(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    schema = load_schema()
    change_dir = resolve_change(args.change)
    states = artifact_states(change_dir, schema)
    artifacts = [
        {
            'id': artifact['id'],
            'outputPath': artifact['generates'],
            'status': states[artifact['id']],
        }
        for artifact in ordered_artifacts(schema)
    ]
    return EXIT_OK, {
        'changeName': change_dir.name,
        'schemaName': schema['name'],
        'isComplete': all(item['status'] == 'done' for item in artifacts),
        'applyRequires': list(schema['apply']['requires']),
        'artifacts': artifacts,
    }


def _apply_payload(change_dir: Path, schema: dict[str, Any]) -> dict[str, Any]:
    states = artifact_states(change_dir, schema)
    complete, total = count_tasks(change_dir)
    tasks: list[dict[str, Any]] = []
    tasks_file = change_dir / schema['apply']['tracks']
    if tasks_file.is_file():
        for line in tasks_file.read_text(encoding='utf-8').splitlines():
            match = CHECKBOX_RE.match(line)
            if match:
                tasks.append(
                    {
                        'id': str(len(tasks) + 1),
                        'description': match.group(2).strip(),
                        'done': match.group(1).lower() == 'x',
                    }
                )
    requires = schema['apply']['requires']
    ready = all(states.get(dep) == 'done' for dep in requires)
    context_files: dict[str, str | list[str]] = {}
    context_findings: list[dict[str, str]] = []
    for artifact in _artifacts(schema):
        context_path, findings = _apply_context_path(
            change_dir, artifact['generates']
        )
        context_files[artifact['id']] = context_path
        context_findings.extend(
            {'artifact': artifact['id'], **finding} for finding in findings
        )
    return {
        'changeName': change_dir.name,
        'changeDir': str(change_dir),
        'schemaName': schema['name'],
        'contextFiles': context_files,
        'contextFindings': context_findings,
        'progress': {
            'total': total,
            'complete': complete,
            'remaining': total - complete,
        },
        'tasks': tasks,
        'state': 'ready' if ready and not context_findings else 'blocked',
        'instruction': _schema_text(
            'instructions', schema['apply']['instruction']
        ),
    }


def cmd_instructions(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    schema = load_schema()
    change_dir = resolve_change(args.change)
    if args.artifact == APPLY_ID:
        payload = _apply_payload(change_dir, schema)
        return (
            EXIT_FINDINGS if payload['contextFindings'] else EXIT_OK,
            payload,
        )
    artifact = _artifact_by_id(schema, args.artifact)
    states = artifact_states(change_dir, schema)
    context, rules = load_authoring_config()
    dependencies = [
        {
            'id': dep,
            'done': states.get(dep) == 'done',
            'path': _artifact_by_id(schema, dep)['generates'],
            'description': _artifact_by_id(schema, dep)['description'],
        }
        for dep in artifact.get('requires', [])
    ]
    return EXIT_OK, {
        'changeName': change_dir.name,
        'artifactId': artifact['id'],
        'schemaName': schema['name'],
        'changeDir': str(change_dir),
        'outputPath': artifact['generates'],
        'description': artifact['description'],
        'instruction': _schema_text('instructions', artifact['instruction']),
        'context': context,
        'rules': rules.get(artifact['id'], []),
        'template': _schema_text('templates', artifact['template']),
        'dependencies': dependencies,
        'unlocks': unlocked_by(schema, artifact['id']),
    }


def cmd_new(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    schema = load_schema()
    name = args.name
    if not CHANGE_NAME_RE.match(name):
        raise ValueError(f'nome invalido (use kebab-case): {name}')
    change_dir = CHANGES_ROOT / name
    if change_dir.exists():
        raise FileExistsError(f'change ja existe: {change_dir}')
    source_type = getattr(args, 'decision_source_type', None)
    source_path = getattr(args, 'decision_source_path', None)
    source_digest = getattr(args, 'decision_source_sha256', None)
    confirmed_on = getattr(args, 'confirmed_on', None)
    decision_ids = getattr(args, 'decision_id', None) or []
    depends_on = getattr(args, 'depends_on', None) or []
    source_values = (
        source_type,
        source_path,
        source_digest,
        confirmed_on,
        decision_ids,
    )
    if not all(source_values):
        raise ValueError(
            'OpenSpec changes require type, path, sha256, confirmed_on, and at least one decision_id'
        )
    created = dt.datetime.now(dt.UTC).date().isoformat()
    manifest_lines = [
        f'schema: {schema["name"]}',
        f'created: {created}',
        'decision_source:',
        f'  type: {source_type}',
        f'  path: {source_path}',
        f'  sha256: {source_digest}',
        f'  confirmed_on: {confirmed_on}',
        '  decision_ids: [' + ', '.join(decision_ids) + ']',
        '  depends_on: [' + ', '.join(depends_on) + ']',
    ]
    change_dir.mkdir(parents=True)
    try:
        (change_dir / '.openspec.yaml').write_text(
            '\n'.join(manifest_lines) + '\n', encoding='utf-8'
        )
        _, findings = validate_decision_source(change_dir)
        if findings:
            summary = '; '.join(item['message'] for item in findings)
            raise ValueError(f'decision-source preflight failed: {summary}')
    except Exception:
        manifest_path = change_dir / '.openspec.yaml'
        if manifest_path.exists():
            manifest_path.unlink()
        change_dir.rmdir()
        raise
    first = ordered_artifacts(schema)[0]
    return EXIT_OK, {
        'changeName': name,
        'changeDir': str(change_dir),
        'schemaName': schema['name'],
        'created': created,
        'nextArtifact': first['id'],
    }


def _finding(
    spec_id: str, requirement: str, code: str, message: str
) -> dict[str, str]:
    return {
        'spec': spec_id,
        'requirement': requirement,
        'code': code,
        'message': message,
    }


def parse_spec_blocks(lines: list[str]) -> list[SpecRequirement]:
    """Divide a spec em requisitos, cada um com preambulo e cenarios."""
    blocks: list[SpecRequirement] = []
    for line in lines:
        if match := GATE.REQUIREMENT_RE.match(line):
            blocks.append(SpecRequirement(name=match.group(1)))
        elif not blocks:
            continue
        elif match := GATE.SCENARIO_RE.match(line):
            blocks[-1].scenarios.append((match.group(1), []))
        elif blocks[-1].scenarios:
            blocks[-1].scenarios[-1][1].append(line)
        else:
            blocks[-1].preamble.append(line)
    return blocks


def _requirement_errors(
    spec_id: str, block: SpecRequirement, strict: bool
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not block.scenarios:
        errors.append(
            _finding(
                spec_id,
                block.name,
                'requirement-without-scenario',
                'requisito sem nenhum `#### Scenario:`',
            )
        )
    preamble = '\n'.join(block.preamble)
    if strict and not NORMATIVE_RE.search(preamble):
        errors.append(
            _finding(
                spec_id,
                block.name,
                'requirement-not-normative',
                'requisito sem SHALL ou MUST no texto',
            )
        )
    for name, body in block.scenarios:
        text = '\n'.join(body)
        missing = [
            token
            for token, pattern in (('WHEN', WHEN_RE), ('THEN', THEN_RE))
            if not pattern.search(text)
        ]
        if missing:
            errors.append(
                _finding(
                    spec_id,
                    block.name,
                    'scenario-incomplete',
                    f'cenario {name!r} sem {" e ".join(missing)}',
                )
            )
    return errors


def _validate_spec(path: Path, strict: bool) -> list[dict[str, str]]:
    lines = path.read_text(encoding='utf-8').splitlines()
    spec_id = str(path.relative_to(REPO_ROOT))
    errors = [
        _finding(
            spec_id,
            '',
            'scenario-heading-level',
            'cenario com 3 hashtags; use exatamente 4',
        )
        for line in lines
        if MISPLACED_SCENARIO_RE.match(line)
    ]
    blocks = parse_spec_blocks(lines)
    if not blocks:
        errors.append(
            _finding(
                spec_id,
                '',
                'spec-without-requirement',
                'spec sem nenhum `### Requirement:`',
            )
        )
    for block in blocks:
        errors.extend(_requirement_errors(spec_id, block, strict))
    return errors


def cmd_validate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    paths = sorted(SPECS_ROOT.glob('*/spec.md'))
    errors: list[dict[str, str]] = []
    for path in paths:
        errors.extend(_validate_spec(path, args.strict))
    return (
        EXIT_FINDINGS if errors else EXIT_OK,
        {
            'status': 'error' if errors else 'ok',
            'checked': len(paths),
            'strict': bool(args.strict),
            'errors': errors,
        },
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='opsx', description='Workflow OPSX repo-native.'
    )
    parser.add_argument('--json', action='store_true')
    # `--json` tambem depois do subcomando: SUPPRESS evita que o default do
    # subparser sobrescreva o valor vindo do parser principal.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        '--json', action='store_true', default=argparse.SUPPRESS
    )
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('list', help='changes ativas', parents=[common])
    status = sub.add_parser(
        'status', help='estado dos artefatos', parents=[common]
    )
    status.add_argument('--change', required=True)
    preflight = sub.add_parser(
        'preflight',
        help='validacao de provenance e ownership',
        parents=[common],
    )
    preflight.add_argument('--change', required=True)

    fingerprint = sub.add_parser(
        'fingerprint',
        help='fingerprint do estado atual para evidencia semantica',
        parents=[common],
    )
    fingerprint.add_argument('--change', required=True)

    instructions = sub.add_parser(
        'instructions', help='instrucao autoral', parents=[common]
    )
    instructions.add_argument('artifact')
    instructions.add_argument('--change', required=True)

    new = sub.add_parser('new', help='scaffold de change', parents=[common])
    new.add_argument('kind', choices=['change'])
    new.add_argument('name')
    new.add_argument('--decision-source-type')
    new.add_argument('--decision-source-path')
    new.add_argument('--decision-source-sha256')
    new.add_argument('--confirmed-on')
    new.add_argument('--decision-id', action='append', default=[])
    new.add_argument('--depends-on', action='append', default=[])

    validate = sub.add_parser(
        'validate', help='formato das specs', parents=[common]
    )
    validate.add_argument('--specs', action='store_true')
    validate.add_argument('--strict', action='store_true')
    return parser


HANDLERS = {
    'list': cmd_list,
    'status': cmd_status,
    'preflight': cmd_preflight,
    'fingerprint': cmd_fingerprint,
    'instructions': cmd_instructions,
    'new': cmd_new,
    'validate': cmd_validate,
}


def _print_human(command: str, payload: dict[str, Any]) -> None:
    if command == 'list':
        for change in payload['changes']:
            print(
                f'  {change["name"]:<45}'
                f' {change["completedTasks"]}/{change["totalTasks"]} tasks'
                f'   {change["status"]}'
            )
        return
    if command == 'status':
        print(f'{payload["changeName"]} ({payload["schemaName"]})')
        for artifact in payload['artifacts']:
            print(f'  {artifact["status"]:<8} {artifact["id"]}')
        return
    if command == 'validate':
        for error in payload['errors']:
            print(
                f'error [{error["code"]}] {error["spec"]}: {error["message"]}'
            )
        print(f'{payload["status"]} | {payload["checked"]} specs')
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload = HANDLERS[args.command](args)
    except (FileNotFoundError, FileExistsError, KeyError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(args.command, payload)
    return code


if __name__ == '__main__':
    sys.exit(main())
