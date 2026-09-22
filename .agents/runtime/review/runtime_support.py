#!/usr/bin/env python3
"""Shared runtime for the project-agnostic review protocol."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.paths import repo_root
from harness.selection import load_review_owner

CURRENT_SCHEMA_VERSION = '1.0.0'
HARNESS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = repo_root()
AGENTS_ROOT = HARNESS_ROOT
SESSIONS_ROOT = REPO_ROOT / '.agents' / 'sessions'
REVIEW_RUNTIME_ROOT = AGENTS_ROOT / 'runtime' / 'review'
SKILLS_ROOT = AGENTS_ROOT / 'skills'
LINT_AND_VALIDATE_ROOT = SKILLS_ROOT / 'lint-and-validate'
REVIEW_OWNER_PATH = AGENTS_ROOT / 'harness' / 'review-owner.json'
REVIEW_OWNER = load_review_owner(REVIEW_OWNER_PATH)
REVIEW_OWNER_ROOT = (
    SKILLS_ROOT / REVIEW_OWNER.split('/', 1)[1]
    if REVIEW_OWNER is not None
    else None
)
PACK_REGISTRY_PATH = REVIEW_RUNTIME_ROOT / 'pack-registry.json'

TEMPLATE_PATHS = {
    'gate-report.template.md': (
        LINT_AND_VALIDATE_ROOT / 'templates/gate-report.template.md'
    ),
}

ARTIFACT_SCHEMA_PATHS = {
    'gate-report': LINT_AND_VALIDATE_ROOT / 'schemas/gate-report.schema.json',
}

if REVIEW_OWNER_ROOT is not None:
    TEMPLATE_PATHS.update(
        {
            'review-session.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'review-session.template.md',
            'review-plan.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'review-plan.template.md',
            'finding.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'finding.template.md',
            'security-handoff.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'security-handoff.template.md',
            'verdict.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'verdict.template.md',
            'review-summary.template.md': REVIEW_OWNER_ROOT
            / 'templates'
            / 'review-summary.template.md',
        }
    )
    ARTIFACT_SCHEMA_PATHS.update(
        {
            'review-session': REVIEW_OWNER_ROOT
            / 'schemas'
            / 'review-session.schema.json',
            'review-plan': REVIEW_OWNER_ROOT
            / 'schemas'
            / 'review-plan.schema.json',
            'finding': REVIEW_OWNER_ROOT / 'schemas' / 'finding.schema.json',
            'security-handoff': REVIEW_OWNER_ROOT
            / 'schemas'
            / 'security-handoff.schema.json',
            'verdict': REVIEW_OWNER_ROOT / 'schemas' / 'verdict.schema.json',
        }
    )

SESSION_STATUSES = {
    'initialized',
    'planned',
    'reviewing',
    'awaiting_security',
    'apply-ready',
    'completed',
    'blocked',
}
PLAN_STATUSES = {'draft', 'ready', 'in_review', 'completed'}
PLAN_ITEM_STATUSES = {'pending', 'in_review', 'completed', 'skipped'}
FINDING_STATUSES = {'open', 'accepted', 'dismissed'}
FINDING_SEVERITIES = {'blocker', 'warning', 'nit'}
FINDING_CONFIDENCE = {'high', 'medium', 'low'}
GATE_REPORT_STATUSES = {'pending', 'running', 'completed'}
GATE_STATUSES = {'pending', 'passed', 'failed', 'skipped', 'external_failure'}
VERDICT_STATUSES = {'draft', 'final'}
VERDICT_VALUES = {
    'APPROVED',
    'CHANGES_REQUIRED',
    'SECURITY_REVIEW_REQUIRED',
    'INCOMPLETE',
}
SECURITY_HANDOFF_STATUSES = {
    'pending',
    'in_review',
    'cleared',
    'changes_required',
    'waived',
}
NON_TERMINAL_SECURITY_STATUSES = {'pending', 'in_review'}

PACK_REGISTRY = (
    json.loads(PACK_REGISTRY_PATH.read_text(encoding='utf-8'))
    if REVIEW_OWNER is not None
    else {}
)


class ArtifactError(ValueError):
    """Raised when review artifacts violate the protocol contract."""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_repo_path(value: str) -> str:
    path = Path(value)
    candidate = path if path.is_absolute() else REPO_ROOT / path
    try:
        return candidate.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ArtifactError(
            f'repository path must stay inside the repository: {value!r}'
        ) from exc


def normalize_paths(values: list[str]) -> list[str]:
    return sorted({normalize_repo_path(value) for value in values})


def make_review_id(prefix: str = 'review') -> str:
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    return f'{prefix}-{stamp}'


def resolve_session_dir(
    review_id: str | None = None, session_dir: str | None = None
) -> Path:
    if session_dir:
        path = Path(session_dir)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()
    if not review_id:
        review_id = make_review_id()
    return (SESSIONS_ROOT / review_id).resolve()


def ensure_session_layout(session_dir: Path) -> None:
    for child in (
        session_dir,
        session_dir / 'artifacts',
        session_dir / 'artifacts' / 'findings',
        session_dir / 'views',
        session_dir / 'views' / 'findings',
        session_dir / 'logs',
    ):
        child.mkdir(parents=True, exist_ok=True)


def artifact_filename(
    artifact_type: str, artifact_id: str | None = None
) -> Path:
    if artifact_type == 'finding':
        if not artifact_id:
            raise ArtifactError('finding artifact requires artifact_id')
        return Path('artifacts/findings') / f'{artifact_id}.json'
    names = {
        'review-session': 'artifacts/review-session.json',
        'review-plan': 'artifacts/review-plan.json',
        'gate-report': 'artifacts/gate-report.json',
        'security-handoff': 'artifacts/security-handoff.json',
        'verdict': 'artifacts/verdict.json',
    }
    try:
        return Path(names[artifact_type])
    except KeyError as error:
        raise ArtifactError(
            f'unknown artifact type: {artifact_type}'
        ) from error


def view_filename(artifact_type: str, artifact_id: str | None = None) -> Path:
    if artifact_type == 'finding':
        if not artifact_id:
            raise ArtifactError('finding view requires artifact_id')
        return Path('views/findings') / f'{artifact_id}.md'
    names = {
        'review-session': 'views/review-session.md',
        'review-plan': 'views/review-plan.md',
        'gate-report': 'views/gate-report.md',
        'security-handoff': 'views/security-handoff.md',
        'verdict': 'views/verdict.md',
    }
    try:
        return Path(names[artifact_type])
    except KeyError as error:
        raise ArtifactError(
            f'unknown artifact type: {artifact_type}'
        ) from error


def load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        payload: dict[str, Any] = json.load(handle)
    return payload


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write('\n')


def render_template(template_name: str, context: dict[str, Any]) -> str:
    template_path = TEMPLATE_PATHS.get(template_name)
    if template_path is None:
        raise ArtifactError(f'unknown template: {template_name}')
    if not template_path.exists():
        raise ArtifactError(f'missing template: {template_path}')
    raw = template_path.read_text(encoding='utf-8')
    safe_context = {
        key: stringify_template_value(value) for key, value in context.items()
    }
    return Template(raw).safe_substitute(safe_context).rstrip() + '\n'


def stringify_template_value(value: Any) -> str:
    if isinstance(value, list):
        return '\n'.join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    if value is None:
        return ''
    return str(value)


def write_view(session_dir: Path, artifact: dict[str, Any]) -> Path:
    artifact_type = artifact['artifactType']
    artifact_id = artifact.get('findingId')
    output_path = session_dir / view_filename(artifact_type, artifact_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_human_view(artifact), encoding='utf-8')
    return output_path


def render_human_view(artifact: dict[str, Any]) -> str:
    artifact_type = artifact['artifactType']
    if artifact_type == 'review-session':
        return render_template(
            'review-session.template.md',
            {
                'reviewId': artifact['reviewId'],
                'status': artifact['status'],
                'schemaVersion': artifact['schemaVersion'],
                'changeType': artifact['change']['changeType'],
                'changedBy': artifact['change']['changedBy'],
                'securityTouch': artifact['change']['securityTouch'],
                'changedFiles': [
                    f'- {item}' for item in artifact['changedFiles']
                ],
                'stats': [
                    f'- total_items: {artifact["statistics"]["totalItems"]}',
                    f'- completed_items: {artifact["statistics"]["completedItems"]}',
                    f'- findings: {artifact["statistics"]["findingCount"]}',
                    f'- blocking_findings: {artifact["statistics"]["blockingFindingCount"]}',
                ],
            },
        )
    if artifact_type == 'review-plan':
        item_lines = []
        for item in artifact['items']:
            item_lines.extend(
                [
                    f'## {item["itemId"]} - {item["topic"]}',
                    f'- status: {item["status"]}',
                    f'- priority: {item["priority"]}',
                    f'- pack: {item["packId"]}',
                    f'- files: {", ".join(item["files"])}',
                    f'- skills: {", ".join(item["skills"])}',
                    f'- checklists: {", ".join(item["checklists"])}',
                ],
            )
            if item['expansions']:
                item_lines.append('- expansions:')
                item_lines.extend(
                    f'  - {entry["reason"]} -> {", ".join(entry["files"])}'
                    for entry in item['expansions']
                )
        return render_template(
            'review-plan.template.md',
            {
                'reviewId': artifact['reviewId'],
                'status': artifact['status'],
                'schemaVersion': artifact['schemaVersion'],
                'items': item_lines,
            },
        )
    if artifact_type == 'finding':
        location = artifact['evidence']['file']
        line = artifact['evidence'].get('line')
        if line is not None:
            location = f'{location}:{line}'
        return render_template(
            'finding.template.md',
            {
                'reviewId': artifact['reviewId'],
                'findingId': artifact['findingId'],
                'status': artifact['status'],
                'severity': artifact['severity'],
                'confidence': artifact['confidence'],
                'topic': artifact['topic'],
                'location': location,
                'summary': artifact['summary'],
                'impact': artifact['impact'],
                'recommendedAction': artifact['recommendedAction'],
                'blocking': str(artifact['blocking']).lower(),
            },
        )
    if artifact_type == 'gate-report':
        gate_lines = []
        for gate in artifact['gates']:
            gate_lines.extend(
                [
                    f'## {gate["gateId"]}',
                    f'- status: {gate["status"]}',
                    f'- blocking: {str(gate["blocking"]).lower()}',
                    f'- classification: {gate.get("classification", "code")}',
                    f'- exit_code: {gate["exitCode"]}',
                    f'- command: {gate["command"]}',
                    f'- duration_seconds: {gate["durationSeconds"]}',
                ],
            )
        return render_template(
            'gate-report.template.md',
            {
                'reviewId': artifact['reviewId'],
                'status': artifact['status'],
                'schemaVersion': artifact['schemaVersion'],
                'effectiveProfile': artifact.get('effectiveProfile', ''),
                'gates': gate_lines,
            },
        )
    if artifact_type == 'security-handoff':
        return render_template(
            'security-handoff.template.md',
            {
                'reviewId': artifact['reviewId'],
                'status': artifact['status'],
                'targetAgent': artifact['targetAgent'],
                'reason': artifact['reason'],
                'affectedFiles': [
                    f'- {item}' for item in artifact['affectedFiles']
                ],
                'evidenceIds': [
                    f'- {item}' for item in artifact['evidenceIds']
                ],
            },
        )
    if artifact_type == 'verdict':
        return render_template(
            'verdict.template.md',
            {
                'reviewId': artifact['reviewId'],
                'status': artifact['status'],
                'verdict': artifact['verdict'],
                'summary': artifact['summary'],
                'blockingReasons': [
                    f'- {item}' for item in artifact['blockingReasons']
                ],
                'advisories': [f'- {item}' for item in artifact['advisories']],
                'securityOutcome': artifact.get(
                    'securityOutcome', 'not_requested'
                ),
            },
        )
    raise ArtifactError(f'unsupported view for {artifact_type}')


def load_or_migrate_artifact(
    session_dir: Path, artifact_type: str, artifact_id: str | None = None
) -> dict[str, Any]:
    path = session_dir / artifact_filename(artifact_type, artifact_id)
    payload = load_json(path)
    migrated = migrate_artifact(payload)
    validate_artifact(migrated)
    if migrated != payload:
        dump_json(path, migrated)
        write_view(session_dir, migrated)
    return migrated


def migrate_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get('schemaVersion')
    if version == CURRENT_SCHEMA_VERSION:
        return payload
    if version != '0.9.0':
        raise ArtifactError(
            f'incompatible-artifact: unsupported schemaVersion {version!r}',
        )
    migrated = deepcopy(payload)
    migrated['schemaVersion'] = CURRENT_SCHEMA_VERSION
    if 'type' in migrated and 'artifactType' not in migrated:
        migrated['artifactType'] = migrated.pop('type')
    if 'review_id' in migrated and 'reviewId' not in migrated:
        migrated['reviewId'] = migrated.pop('review_id')
    if migrated['artifactType'] == 'finding' and 'evidence' not in migrated:
        migrated['evidence'] = {
            'file': migrated.pop('file'),
            'line': migrated.pop('line', None),
            'snippet': migrated.pop('evidenceSnippet', ''),
        }
    return migrated


def validate_status(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ArtifactError(
            f'{name} must be one of {sorted(allowed)}, got {value!r}'
        )


def expect_fields(payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ArtifactError(f'missing required fields: {", ".join(missing)}')


def validate_artifact(payload: dict[str, Any]) -> None:
    expect_fields(
        payload, ['artifactType', 'schemaVersion', 'reviewId', 'status']
    )
    if payload['schemaVersion'] != CURRENT_SCHEMA_VERSION:
        raise ArtifactError('artifact must be migrated before validation')
    schema_path = ARTIFACT_SCHEMA_PATHS.get(payload['artifactType'])
    if schema_path is None:
        raise ArtifactError(
            f'unknown artifact type: {payload["artifactType"]}'
        )
    if not schema_path.exists():
        raise ArtifactError(f'missing schema: {schema_path}')
    validators = {
        'review-session': validate_review_session,
        'review-plan': validate_review_plan,
        'finding': validate_finding,
        'gate-report': validate_gate_report,
        'security-handoff': validate_security_handoff,
        'verdict': validate_verdict,
    }
    validators[payload['artifactType']](payload)


def validate_review_session(payload: dict[str, Any]) -> None:
    validate_status(
        'review-session.status', payload['status'], SESSION_STATUSES
    )
    expect_fields(
        payload,
        ['createdAt', 'updatedAt', 'change', 'changedFiles', 'statistics'],
    )
    expect_fields(
        payload['change'], ['changeType', 'changedBy', 'securityTouch']
    )
    expect_fields(
        payload['statistics'],
        [
            'totalItems',
            'completedItems',
            'findingCount',
            'blockingFindingCount',
        ],
    )


def validate_review_plan(payload: dict[str, Any]) -> None:
    validate_status('review-plan.status', payload['status'], PLAN_STATUSES)
    expect_fields(payload, ['createdAt', 'updatedAt', 'items'])
    for item in payload['items']:
        expect_fields(
            item,
            [
                'itemId',
                'topic',
                'priority',
                'packId',
                'status',
                'files',
                'skills',
                'checklists',
                'contextFiles',
                'expansions',
            ],
        )
        validate_status(
            'review-plan.items.status', item['status'], PLAN_ITEM_STATUSES
        )
        if item['packId'] not in PACK_REGISTRY:
            raise ArtifactError(f'unknown packId {item["packId"]!r}')


def validate_finding(payload: dict[str, Any]) -> None:
    validate_status('finding.status', payload['status'], FINDING_STATUSES)
    validate_status(
        'finding.severity', payload['severity'], FINDING_SEVERITIES
    )
    validate_status(
        'finding.confidence', payload['confidence'], FINDING_CONFIDENCE
    )
    expect_fields(
        payload,
        [
            'findingId',
            'topic',
            'summary',
            'impact',
            'recommendedAction',
            'blocking',
            'evidence',
        ],
    )
    expect_fields(payload['evidence'], ['file', 'snippet'])


def validate_gate_report(payload: dict[str, Any]) -> None:
    validate_status(
        'gate-report.status', payload['status'], GATE_REPORT_STATUSES
    )
    expect_fields(payload, ['createdAt', 'updatedAt', 'gates'])
    for gate in payload['gates']:
        expect_fields(
            gate,
            [
                'gateId',
                'label',
                'command',
                'blocking',
                'status',
                'startedAt',
                'finishedAt',
                'durationSeconds',
                'exitCode',
                'outcome',
            ],
        )
        validate_status('gate.status', gate['status'], GATE_STATUSES)


def validate_security_handoff(payload: dict[str, Any]) -> None:
    validate_status(
        'security-handoff.status', payload['status'], SECURITY_HANDOFF_STATUSES
    )
    expect_fields(
        payload,
        [
            'createdAt',
            'updatedAt',
            'targetAgent',
            'requestedBy',
            'reason',
            'affectedFiles',
            'evidenceIds',
        ],
    )


def validate_verdict(payload: dict[str, Any]) -> None:
    validate_status('verdict.status', payload['status'], VERDICT_STATUSES)
    validate_status('verdict.value', payload['verdict'], VERDICT_VALUES)
    expect_fields(
        payload, ['summary', 'blockingReasons', 'advisories', 'metrics']
    )


def save_artifact(session_dir: Path, artifact: dict[str, Any]) -> Path:
    validate_artifact(artifact)
    path = session_dir / artifact_filename(
        artifact['artifactType'], artifact.get('findingId')
    )
    dump_json(path, artifact)
    write_view(session_dir, artifact)
    return path


def list_findings(session_dir: Path) -> list[dict[str, Any]]:
    findings_dir = session_dir / 'artifacts' / 'findings'
    if not findings_dir.exists():
        return []
    return [
        load_or_migrate_artifact(session_dir, 'finding', path.stem)
        for path in sorted(findings_dir.glob('*.json'))
    ]


def update_session_statistics(session_dir: Path) -> dict[str, Any]:
    session = load_or_migrate_artifact(session_dir, 'review-session')
    plan = load_or_migrate_artifact(session_dir, 'review-plan')
    findings = list_findings(session_dir)
    session['statistics'] = {
        'totalItems': len(plan['items']),
        'completedItems': sum(
            1 for item in plan['items'] if item['status'] == 'completed'
        ),
        'findingCount': len(findings),
        'blockingFindingCount': sum(
            1 for finding in findings if finding['blocking']
        ),
    }
    session['updatedAt'] = now_iso()
    save_artifact(session_dir, session)
    return session


def assert_transition(
    artifact_type: str,
    current_status: str,
    next_status: str,
) -> None:
    transitions = {
        'review-session': {
            'initialized': {'planned', 'blocked'},
            'planned': {'reviewing', 'apply-ready', 'completed', 'blocked'},
            'reviewing': {
                'awaiting_security',
                'apply-ready',
                'completed',
                'blocked',
            },
            'awaiting_security': {'apply-ready', 'completed', 'blocked'},
            'apply-ready': {
                'reviewing',
                'awaiting_security',
                'completed',
                'blocked',
            },
            'completed': set(),
            'blocked': {'planned', 'reviewing'},
        },
        'review-plan': {
            'draft': {'ready'},
            'ready': {'in_review', 'completed'},
            'in_review': {'completed'},
            'completed': set(),
        },
        'gate-report': {
            'pending': {'running', 'completed'},
            'running': {'completed'},
            'completed': set(),
        },
        'security-handoff': {
            'pending': {'in_review', 'cleared', 'changes_required', 'waived'},
            'in_review': {'cleared', 'changes_required', 'waived'},
            'cleared': set(),
            'changes_required': set(),
            'waived': set(),
        },
        'verdict': {
            'draft': {'final'},
            'final': set(),
        },
    }
    allowed = transitions.get(artifact_type, {})
    if next_status not in allowed.get(current_status, set()):
        raise ArtifactError(
            f'invalid transition for {artifact_type}: {current_status!r} -> {next_status!r}',
        )


def build_empty_plan(review_id: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        'artifactType': 'review-plan',
        'schemaVersion': CURRENT_SCHEMA_VERSION,
        'reviewId': review_id,
        'status': 'draft',
        'createdAt': stamp,
        'updatedAt': stamp,
        'items': [],
    }


def build_empty_gate_report(review_id: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        'artifactType': 'gate-report',
        'schemaVersion': CURRENT_SCHEMA_VERSION,
        'reviewId': review_id,
        'status': 'pending',
        'createdAt': stamp,
        'updatedAt': stamp,
        'gates': [],
    }


def build_default_verdict(review_id: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        'artifactType': 'verdict',
        'schemaVersion': CURRENT_SCHEMA_VERSION,
        'reviewId': review_id,
        'status': 'draft',
        'createdAt': stamp,
        'updatedAt': stamp,
        'verdict': 'INCOMPLETE',
        'summary': 'Review ainda nao consolidado.',
        'blockingReasons': [],
        'advisories': [],
        'securityOutcome': 'not_requested',
        'metrics': {
            'blockingFindings': 0,
            'warningFindings': 0,
            'nitFindings': 0,
            'failedBlockingGates': 0,
            'failedAdvisoryGates': 0,
        },
    }


def detect_packs(changed_files: list[str], security_touch: str) -> list[str]:
    if not PACK_REGISTRY:
        return []
    matched = set()
    for file_path in changed_files:
        lower = file_path.lower()
        if security_touch == 'yes' or any(
            token in lower
            for token in (
                'auth',
                'credential',
                'permission',
                'policy',
                'secret',
                'session',
                'token',
                'upload',
            )
        ):
            matched.add('security')
        if any(
            token in lower
            for token in (
                'api',
                'cli',
                'contract',
                'controller',
                'endpoint',
                'handler',
                'interface',
                'route',
                'schema',
            )
        ):
            matched.add('interface')
        if any(
            token in lower
            for token in (
                'data',
                'db',
                'migration',
                'model',
                'parquet',
                'query',
                'repository',
                'schema',
                'sql',
            )
        ):
            matched.add('data')
        if any(
            token in lower
            for token in (
                'scripts/',
                'src/',
                'service',
                'core',
                'domain',
                'runtime',
                'worker',
                'lock',
            )
        ):
            matched.add('behavior')
        if '/tests/' in lower or lower.startswith('tests/'):
            matched.add('tests')
        if lower.endswith(('.md', '.rst', '.txt')) or '/docs/' in lower:
            matched.add('docs')
    return sorted(
        matched, key=lambda pack_id: -PACK_REGISTRY[pack_id]['priority']
    )


def build_plan_items(
    changed_files: list[str], security_touch: str
) -> list[dict[str, Any]]:
    normalized_files = normalize_paths(changed_files)
    items = []
    for index, pack_id in enumerate(
        detect_packs(normalized_files, security_touch), start=1
    ):
        pack = PACK_REGISTRY[pack_id]
        item_files = [
            file_path
            for file_path in normalized_files
            if pack_id in detect_packs([file_path], security_touch)
        ]
        items.append(
            {
                'itemId': f'RVI-{index:03d}',
                'topic': pack['topic'],
                'priority': pack['priority'],
                'packId': pack_id,
                'status': 'pending',
                'files': item_files,
                'skills': pack['skills'],
                'checklists': pack['checklists'],
                'contextFiles': item_files,
                'expansions': [],
            },
        )
    return items


def validate_context_expansion(
    existing_files: list[str], requested_files: list[str]
) -> list[str]:
    normalized_existing = [Path(path) for path in existing_files]
    approved = []
    for raw_file in requested_files:
        candidate = Path(normalize_repo_path(raw_file))
        if candidate.as_posix() in {
            path.as_posix() for path in normalized_existing
        }:
            approved.append(candidate.as_posix())
            continue
        allowed = False
        for current in normalized_existing:
            same_parent = candidate.parent == current.parent
            parent_child = (
                candidate.parent == current or current.parent == candidate
            )
            near_subtree = (
                len(candidate.parents) > 1
                and candidate.parents[1] == current.parent
            ) or (
                len(current.parents) > 1
                and current.parents[1] == candidate.parent
            )
            same_stem = candidate.stem == current.stem
            if same_parent or parent_child or near_subtree or same_stem:
                allowed = True
                break
        if not allowed:
            raise ArtifactError(
                f'context expansion must stay adjacent to current evidence, got {candidate.as_posix()}',
            )
        approved.append(candidate.as_posix())
    approved = sorted(set(approved))
    if len(approved) > 3:
        raise ArtifactError(
            'context expansion supports at most 3 extra files per request'
        )
    return approved
