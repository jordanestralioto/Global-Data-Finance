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
import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness import change_manifest, decision_provenance, handoff
from harness.change_manifest import load_change_manifest
from harness.decision_source import DATE_RE
from harness.paths import HARNESS_ROOT

REPO_ROOT: Path = handoff.REPO_ROOT
CHANGES_ROOT: Path = handoff.CHANGES_ROOT
NON_CHANGE_DIRS: frozenset[str] = frozenset(handoff.NON_CHANGE_DIRS)
SUPPORTED_SCHEMA: str = handoff.SUPPORTED_SCHEMA

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
    return change_manifest.iter_change_dirs(CHANGES_ROOT)


def resolve_change(name: str) -> Path:
    path = CHANGES_ROOT / name
    if not path.is_dir() or name in NON_CHANGE_DIRS:
        raise FileNotFoundError(f'change nao encontrada: {name}')
    return path


def validate_decision_source(
    change_dir: Path, change_dirs: list[Path] | None = None
) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    """Bind shared provenance validation to the CLI's target repository."""
    decision_dirs = (
        change_dirs
        if change_dirs is not None
        else change_manifest.iter_decision_change_dirs(CHANGES_ROOT)
    )
    return decision_provenance.validate_decision_source(
        REPO_ROOT, change_dir, decision_dirs
    )


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
        'repositoryFingerprint': handoff.current_repository_fingerprint(
            exclude_paths=handoff.evidence_exclusions()
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
    created = datetime.datetime.now(datetime.UTC).date().isoformat()
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
        if match := handoff.REQUIREMENT_RE.match(line):
            blocks.append(SpecRequirement(name=match.group(1)))
        elif not blocks:
            continue
        elif match := handoff.SCENARIO_RE.match(line):
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
