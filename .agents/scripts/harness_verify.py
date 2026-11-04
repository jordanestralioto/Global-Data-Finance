"""Produce and re-verify the per-change gate evidence of this harness.

A change is complete only when a current, structured report proves every
blocking gate passed against the working tree as it stands. The gate
contract is read from `.pre-commit-config.yaml`; a report claiming a
different blocking level is rejected. The report carries a working-tree
fingerprint, so evidence stops being valid the moment the code changes.

The verify path runs under interpreters this repository does not control,
so nothing here may import a third-party package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.paths import repo_root

HARNESS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = repo_root()
PRECOMMIT_CONFIG = REPO_ROOT / '.pre-commit-config.yaml'

EVIDENCE_SCHEMA_VERSION = '1.0.0'
EVIDENCE_ARTIFACT_TYPE = 'gate-report'
EFFECTIVE_PROFILE = 'harness'

EVIDENCE_PATH_RE = re.compile(
    r'^openspec/changes/[^/]+/evidence/gate-report\.json$'
)
EVIDENCE_REPORT_RE = re.compile(
    r'^openspec/changes/[^/]+/evidence/'
    r'(?:gate-report|verification-report)\.json$'
)
# Parse the simple hook roster without third-party dependencies.
HOOK_ID_RE = re.compile(r'^\s*-\s+id:\s*([A-Za-z0-9._-]+)\s*$')
COMMIT_MSG_SAMPLE = 'feat(harness): synthetic commit-msg gate evidence\n'


class EvidenceError(Exception):
    """The evidence cannot be trusted, with the reason as the message."""


def _git(args: list[str]) -> str:
    completed = subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise EvidenceError(f'git {" ".join(args)} failed')
    return completed.stdout


def git_head() -> str:
    head = _git(['rev-parse', 'HEAD']).strip()
    if not head:
        raise EvidenceError('unable to resolve git HEAD')
    return head


def _stage_hooks(stage: str) -> set[str]:
    pattern = re.compile(rf'^\s*stages:\s*\[[^\]]*{stage}')
    hooks: set[str] = set()
    current = ''
    for line in PRECOMMIT_CONFIG.read_text(encoding='utf-8').splitlines():
        match = HOOK_ID_RE.match(line)
        if match:
            current = match.group(1)
        elif pattern.match(line):
            hooks.add(current)
    return hooks


def commit_msg_hooks() -> set[str]:
    """Hook ids declared for the commit-msg stage."""
    return _stage_hooks('commit-msg')


def pre_push_hooks() -> set[str]:
    """Hook ids declared for the pre-push stage."""
    return _stage_hooks('pre-push')


def manual_hooks() -> set[str]:
    """Hook ids declared for the manual stage."""
    return _stage_hooks('manual')


def normalize_repo_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        path = path.resolve().relative_to(REPO_ROOT)
    normalized = path.as_posix()
    return normalized[2:] if normalized.startswith('./') else normalized


def resolve_evidence_path(raw_path: str) -> tuple[Path, str]:
    candidate = Path(raw_path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (REPO_ROOT / candidate).resolve()
    )
    try:
        relative = resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise EvidenceError(
            'evidence path must stay inside the repository'
        ) from exc
    if not EVIDENCE_PATH_RE.match(relative):
        raise EvidenceError(
            'evidence path must be '
            'openspec/changes/<name>/evidence/gate-report.json'
        )
    return resolved, relative


def detect_changed_files() -> list[str]:
    changed: set[str] = set()
    for args in (
        ['diff', '--name-only', '--cached'],
        ['diff', '--name-only'],
        ['ls-files', '--others', '--exclude-standard'],
    ):
        changed |= {
            normalize_repo_path(line)
            for line in _git(args).splitlines()
            if line.strip()
        }
    return sorted(changed)


def _path_state(repo_path: str) -> dict[str, str]:
    path = REPO_ROOT / repo_path
    if path.is_symlink():
        digest = hashlib.sha256(os.readlink(path).encode('utf-8')).hexdigest()
        return {'path': repo_path, 'kind': 'symlink', 'sha256': digest}
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {'path': repo_path, 'kind': 'file', 'sha256': digest}
    kind = 'other' if path.exists() else 'missing'
    return {'path': repo_path, 'kind': kind, 'sha256': ''}


def hook_contract() -> dict[str, bool]:
    if not PRECOMMIT_CONFIG.is_file():
        raise EvidenceError('.pre-commit-config.yaml is missing')
    contract: dict[str, bool] = {}
    for line in PRECOMMIT_CONFIG.read_text(encoding='utf-8').splitlines():
        match = HOOK_ID_RE.match(line)
        if match:
            contract[match.group(1)] = True
    if not contract:
        raise EvidenceError('.pre-commit-config.yaml declares no gate')
    return contract


def evidence_excluded_paths(evidence_relative_path: str) -> list[str]:
    excluded = {normalize_repo_path(evidence_relative_path)}
    changes_root = REPO_ROOT / 'openspec' / 'changes'
    if changes_root.is_dir():
        for change_dir in sorted(changes_root.iterdir()):
            if change_dir.is_dir() and change_dir.name != 'archive':
                prefix = f'openspec/changes/{change_dir.name}/evidence'
                excluded.add(f'{prefix}/gate-report.json')
                excluded.add(f'{prefix}/verification-report.json')
    return sorted(excluded)


def _normalized_exit_code(gate: dict[str, Any]) -> int:
    value = gate.get('exitCode')
    if isinstance(value, int):
        return value
    return 0 if gate.get('status') == 'passed' else -1


def _fingerprint_payload(
    *,
    changed_files: list[str],
    gates: list[dict[str, Any]],
    excluded_paths: list[str],
) -> dict[str, Any]:
    tracked = sorted(
        {
            normalize_repo_path(item)
            for item in changed_files
            if normalize_repo_path(item) not in excluded_paths
        }
    )
    return {
        'head': git_head(),
        'files': [_path_state(item) for item in tracked],
        'effectiveProfile': EFFECTIVE_PROFILE,
        'gateContract': [
            {
                'name': str(gate.get('gateId', '')),
                'command': str(gate.get('command', '')),
                'blocking': bool(gate.get('blocking', True)),
                'status': str(gate.get('status', '')),
                'exitCode': _normalized_exit_code(gate),
            }
            for gate in gates
        ],
        'excludedPaths': sorted(excluded_paths),
    }


def state_fingerprint(
    *,
    changed_files: list[str],
    gates: list[dict[str, Any]],
    excluded_paths: list[str],
) -> dict[str, Any]:
    payload = _fingerprint_payload(
        changed_files=changed_files, gates=gates, excluded_paths=excluded_paths
    )
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    return {
        'algorithm': 'sha256',
        'value': hashlib.sha256(encoded).hexdigest(),
        'head': payload['head'],
        'excludedPaths': payload['excludedPaths'],
    }


def run_gate(hook_id: str) -> dict[str, Any]:
    extra: list[str] = []
    message: Path | None = None
    if hook_id in commit_msg_hooks():
        with NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
            handle.write(COMMIT_MSG_SAMPLE)
        message = Path(handle.name)
        extra = [
            '--hook-stage',
            'commit-msg',
            '--commit-msg-filename',
            str(message),
        ]
    elif hook_id in pre_push_hooks():
        extra = ['--hook-stage', 'pre-push']
    elif hook_id in manual_hooks():
        extra = ['--hook-stage', 'manual']
    command = ' '.join(['pre-commit', 'run', '--all-files', *extra, hook_id])
    started, start = datetime.now(UTC), time.monotonic()
    try:
        completed = subprocess.run(
            ['pre-commit', 'run', '--all-files', *extra, hook_id],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        if message is not None:
            message.unlink(missing_ok=True)
    duration, finished = time.monotonic() - start, datetime.now(UTC)
    passed = completed.returncode == 0
    streams = (completed.stdout, completed.stderr)
    output = '\n'.join(filter(None, streams)).strip()
    return {
        'gateId': hook_id,
        'label': hook_id,
        'command': command,
        'blocking': True,
        'status': 'passed' if passed else 'failed',
        'classification': 'code',
        'startedAt': started.isoformat(),
        'finishedAt': finished.isoformat(),
        'durationSeconds': round(duration, 3),
        'exitCode': completed.returncode,
        'outcome': output or ('passed' if passed else 'failed'),
    }


def build_report(
    gates: list[dict[str, Any]], evidence_relative_path: str
) -> dict[str, Any]:
    excluded = evidence_excluded_paths(evidence_relative_path)
    changed_files = [
        item for item in detect_changed_files() if item not in set(excluded)
    ]
    now = datetime.now(UTC).isoformat()
    change_name = Path(evidence_relative_path).parts[2]
    blocking_failed = any(
        gate['blocking'] and gate['status'] != 'passed' for gate in gates
    )
    return {
        'artifactType': EVIDENCE_ARTIFACT_TYPE,
        'schemaVersion': EVIDENCE_SCHEMA_VERSION,
        'reviewId': f'{change_name}-{git_head()[:12]}',
        'status': 'completed',
        'resultStatus': 'failed' if blocking_failed else 'passed',
        'createdAt': now,
        'updatedAt': now,
        'effectiveProfile': EFFECTIVE_PROFILE,
        'changedFiles': changed_files,
        'gates': gates,
        'stateFingerprint': state_fingerprint(
            changed_files=changed_files,
            gates=gates,
            excluded_paths=excluded,
        ),
    }


def _require_shape(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise EvidenceError('evidence root must be a JSON object')
    if report.get('schemaVersion') != EVIDENCE_SCHEMA_VERSION:
        raise EvidenceError('unsupported evidence schemaVersion')
    if report.get('artifactType') != EVIDENCE_ARTIFACT_TYPE:
        raise EvidenceError('invalid evidence artifactType')
    if report.get('status') != 'completed':
        raise EvidenceError('evidence lifecycle status is not completed')
    if report.get('resultStatus') != 'passed':
        raise EvidenceError('resultStatus is not passed')
    for field in ('reviewId', 'createdAt', 'updatedAt', 'effectiveProfile'):
        value = report.get(field)
        if not isinstance(value, str) or not value:
            raise EvidenceError(f'evidence field {field} is missing')
    if not isinstance(report.get('stateFingerprint'), dict):
        raise EvidenceError('stateFingerprint is missing')
    files = report.get('changedFiles')
    if not isinstance(files, list) or not all(
        isinstance(item, str) for item in files
    ):
        raise EvidenceError('changedFiles must be a list of paths')
    return report


def _require_gates(report: dict[str, Any]) -> list[dict[str, Any]]:
    gates = report.get('gates')
    if (
        not isinstance(gates, list)
        or not gates
        or not all(isinstance(gate, dict) for gate in gates)
    ):
        raise EvidenceError('evidence contains no gates')
    blocking = [gate for gate in gates if gate.get('blocking') is True]
    if not blocking:
        raise EvidenceError('evidence contains no blocking gate')
    if any(
        gate.get('status') != 'passed' or gate.get('exitCode') != 0
        for gate in blocking
    ):
        raise EvidenceError('every blocking gate must pass with exitCode 0')
    return gates


def _require_contract(gates: list[dict[str, Any]]) -> None:
    """The repository decides what blocks, never the report."""
    contract = hook_contract()
    recorded = {str(gate.get('gateId')) for gate in gates}
    missing = sorted(set(contract) - recorded)
    if missing:
        raise EvidenceError(
            'evidence omits declared gates: ' + ', '.join(missing)
        )
    demoted = sorted(
        str(gate.get('gateId'))
        for gate in gates
        if str(gate.get('gateId')) in contract
        and bool(gate.get('blocking')) != contract[str(gate.get('gateId'))]
    )
    if demoted:
        raise EvidenceError(
            'gate blocking level diverges from the contract: '
            + ', '.join(demoted)
        )


def _require_freshness(
    report: dict[str, Any], gates: list[dict[str, Any]], relative_path: str
) -> None:
    recorded = report['stateFingerprint']
    excluded = recorded.get('excludedPaths')
    if not isinstance(excluded, list) or not all(
        isinstance(item, str) for item in excluded
    ):
        raise EvidenceError('stateFingerprint.excludedPaths is missing')
    if not all(EVIDENCE_REPORT_RE.match(item) for item in excluded):
        raise EvidenceError(
            'excludedPaths may only hold derived evidence reports'
        )
    if normalize_repo_path(relative_path) not in excluded:
        raise EvidenceError(
            'stateFingerprint does not exclude its own evidence'
        )
    observed = [
        item for item in detect_changed_files() if item not in set(excluded)
    ]
    if sorted(report['changedFiles']) != sorted(observed):
        raise EvidenceError('changedFiles does not match the repository state')
    current = state_fingerprint(
        changed_files=report['changedFiles'],
        gates=gates,
        excluded_paths=excluded,
    )
    if recorded != current:
        raise EvidenceError(
            'state fingerprint does not match current repository state'
        )


def verify_evidence(raw_path: str) -> str:
    evidence_path, relative_path = resolve_evidence_path(raw_path)
    try:
        report = json.loads(evidence_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(str(exc)) from exc
    report = _require_shape(report)
    gates = _require_gates(report)
    _require_contract(gates)
    _require_freshness(report, gates, relative_path)
    return 'evidence is current and every blocking gate passed'


def _run_gates(relative_path: str) -> tuple[bool, str]:
    contract = hook_contract()
    gates = [run_gate(hook_id) for hook_id in contract]
    evidence_path = REPO_ROOT / relative_path
    report = build_report(gates, relative_path)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    failed = [gate['gateId'] for gate in gates if gate['status'] != 'passed']
    if failed:
        return False, 'failing gates: ' + ', '.join(failed)
    return True, f'{len(gates)} gates passed'


def produce_evidence(raw_path: str) -> tuple[bool, str]:
    _, relative_path = resolve_evidence_path(raw_path)
    return _run_gates(relative_path)


def produce_precomposition_evidence(
    raw_path: str, plan_path_str: str, head_sha: str
) -> tuple[bool, str]:
    evidence_path = REPO_ROOT / raw_path
    plan_path = REPO_ROOT / plan_path_str
    if not plan_path.is_file():
        raise EvidenceError(f'publication plan missing at {plan_path}')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    git_head_sha = _git(['rev-parse', 'HEAD']).strip()
    if git_head_sha != head_sha:
        raise EvidenceError(
            f'HEAD {git_head_sha} != expected precomposition HEAD {head_sha}'
        )
    passed, message = _run_gates(raw_path)
    report = json.loads(evidence_path.read_text(encoding='utf-8'))
    pub_paths = sorted(plan.get('publicationPaths', []))
    comp_digest = hashlib.sha256(
        ''.join(pub_paths).encode('utf-8')
    ).hexdigest()
    report['publication'] = {
        'precompositionHead': head_sha,
        'paths': pub_paths,
        'compositionDigest': f'sha256:{comp_digest}',
    }
    evidence_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    return passed, message


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Produce and verify per-change gate evidence.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--evidence-path', help='run every gate and write report'
    )
    group.add_argument('--verify-evidence', help='re-check an existing report')
    group.add_argument(
        '--precomposition-evidence-path', help='write precomposition report'
    )
    parser.add_argument('--publication-plan', help='cutover plan path')
    parser.add_argument('--precomposition-head', help='expected git HEAD sha')
    args = parser.parse_args()
    try:
        if args.verify_evidence:
            print(verify_evidence(args.verify_evidence))
            return 0
        if args.precomposition_evidence_path:
            if not args.publication_plan or not args.precomposition_head:
                raise EvidenceError(
                    '--publication-plan and --precomposition-head required with --precomposition-evidence-path'
                )
            passed, message = produce_precomposition_evidence(
                args.precomposition_evidence_path,
                args.publication_plan,
                args.precomposition_head,
            )
            print(message)
            return 0 if passed else 1
        passed, message = produce_evidence(args.evidence_path)
    except EvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(message)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
