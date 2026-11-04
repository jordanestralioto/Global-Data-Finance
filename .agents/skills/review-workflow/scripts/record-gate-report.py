#!/usr/bin/env python3
"""Run native validation and record its result in a review session."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from gate_integrity import (
    declared_contract,
    evidence_digest,
    state_fingerprint,
)
from runtime_support import (
    CURRENT_SCHEMA_VERSION,
    REPO_ROOT,
    ArtifactError,
    build_empty_gate_report,
    load_or_migrate_artifact,
    now_iso,
    resolve_session_dir,
    save_artifact,
    validate_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run validation and write the session gate report.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument('--change')
    return parser.parse_args()


def run_gate(
    command: list[str], gate_id: str, *, failure_status: str = 'failed'
) -> dict[str, Any]:
    started_at = now_iso()
    start = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
        )
        exit_code = result.returncode
        status = 'passed' if exit_code == 0 else failure_status
        outcome = f'exit code {exit_code}'
    except OSError as exc:
        exit_code = -1
        status = 'external_failure'
        outcome = str(exc)
    return {
        'gateId': gate_id,
        'label': gate_id,
        'command': shlex.join(command),
        'blocking': True,
        'status': status,
        'classification': 'environment'
        if status == 'external_failure'
        else 'code',
        'startedAt': started_at,
        'finishedAt': now_iso(),
        'durationSeconds': round(time.monotonic() - start, 3),
        'exitCode': exit_code,
        'outcome': outcome,
    }


def evidence_failure(message: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        'gateId': 'review-evidence-import',
        'label': 'review-evidence-import',
        'command': 'validate structured gate evidence',
        'blocking': True,
        'status': 'external_failure',
        'classification': 'environment',
        'startedAt': stamp,
        'finishedAt': stamp,
        'durationSeconds': 0.0,
        'exitCode': -1,
        'outcome': message,
    }


def read_fresh_evidence(
    path: Path, prior_mtime: int | None
) -> tuple[dict[str, Any], str]:
    if not path.is_file() or path.stat().st_mtime_ns == prior_mtime:
        raise ArtifactError('structured evidence was not freshly written')
    try:
        raw = path.read_bytes()
        source = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError('structured evidence is unreadable') from exc
    if not isinstance(source, dict) or source.get('status') != 'completed':
        raise ArtifactError('structured evidence is not completed')
    if source.get('artifactType') != 'gate-report':
        raise ArtifactError('structured evidence is not a gate report')
    if source.get('schemaVersion') != CURRENT_SCHEMA_VERSION:
        raise ArtifactError('structured evidence uses an unsupported schema')
    if not isinstance(source.get('gates'), list) or not source['gates']:
        raise ArtifactError('structured evidence contains no gates')
    try:
        validate_artifact(source)
        if not any(gate['blocking'] for gate in source['gates']):
            raise ArtifactError(
                'structured evidence contains no blocking gate'
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactError(f'structured evidence is invalid: {exc}') from exc
    return source, hashlib.sha256(raw).hexdigest()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    current = load_or_migrate_artifact(session_dir, 'gate-report')
    if current['reviewId'] != session['reviewId']:
        raise SystemExit('gate report belongs to a different review')

    try:
        contract = declared_contract(args.change)
    except ArtifactError as exc:
        raise SystemExit(str(exc)) from exc

    evidence_path = None
    prior_mtime = None
    if contract['mode'] == 'structured':
        evidence_path = REPO_ROOT / contract['evidence']
        if evidence_path.exists():
            prior_mtime = evidence_path.stat().st_mtime_ns
    excluded = (
        (contract['evidence'],) if contract['mode'] == 'structured' else ()
    )
    before_state = state_fingerprint(
        session_dir, session['changedFiles'], excluded
    )

    command_gate = run_gate(contract['command'], 'review-validation-command')
    gates = [command_gate]
    source = None
    source_digest = None
    if evidence_path is not None:
        try:
            source, source_digest = read_fresh_evidence(
                evidence_path, prior_mtime
            )
            gates.extend(source['gates'])
        except ArtifactError as exc:
            gates.append(evidence_failure(str(exc)))
        if source is not None and command_gate['status'] == 'passed':
            verify_gate = run_gate(
                [
                    sys.executable,
                    str(REPO_ROOT / contract['verifier']),
                    '--verify-evidence',
                    str(evidence_path),
                ],
                'review-evidence-verification',
                failure_status='external_failure',
            )
            gates.append(verify_gate)
            try:
                unchanged = evidence_digest(evidence_path) == source_digest
            except OSError:
                unchanged = False
            if not unchanged:
                gates.append(
                    evidence_failure(
                        'structured evidence changed during verification'
                    )
                )

    after_state = state_fingerprint(
        session_dir, session['changedFiles'], excluded
    )
    if before_state != after_state:
        gates.append(evidence_failure('repository changed during validation'))

    report = build_empty_gate_report(session['reviewId'])
    report['createdAt'] = current['createdAt']
    report['status'] = 'completed'
    report['updatedAt'] = now_iso()
    report['gates'] = gates
    report['reviewedFiles'] = session['changedFiles']
    report['validationMode'] = contract['mode']
    report['stateFingerprint'] = after_state
    if source is not None and evidence_path is not None:
        report['sourceEvidencePath'] = contract['evidence']
        report['sourceEvidenceSha256'] = source_digest
        report['effectiveProfile'] = source.get('effectiveProfile', '')
        report['change'] = contract['change']
    save_artifact(session_dir, report)
    passed = all(
        gate['status'] == 'passed' and gate['exitCode'] == 0
        for gate in gates
        if gate['blocking']
    )
    print(
        json.dumps(
            {
                'reviewId': session['reviewId'],
                'status': report['status'],
                'gateCount': len(gates),
                'passed': passed,
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
