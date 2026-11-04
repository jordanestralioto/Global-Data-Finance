#!/usr/bin/env python3
"""Consolidate the final review verdict."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from gate_integrity import recorded_evidence_issue
from runtime_support import (
    CURRENT_SCHEMA_VERSION,
    NON_TERMINAL_SECURITY_STATUSES,
    REPO_ROOT,
    assert_transition,
    list_findings,
    load_or_migrate_artifact,
    now_iso,
    resolve_session_dir,
    save_artifact,
    update_session_statistics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Consolidate the final review verdict.'
    )
    parser.add_argument('--session-dir', required=True)
    return parser.parse_args()


def plan_gaps(session: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    changed_files = set(session['changedFiles'])
    items = plan['items']
    reasons = []
    if not changed_files:
        reasons.append('No changed files were provided for review.')
    if not items:
        reasons.append('The review plan has no items.')
    if plan['status'] != 'completed':
        reasons.append('Review plan is not completed.')
    covered = {path for item in items for path in item['files']}
    missing = sorted(changed_files - covered)
    if missing:
        reasons.append(
            'Files missing from the review plan: ' + ', '.join(missing)
        )
    if any(item['status'] != 'completed' for item in items):
        reasons.append('There are pending review items.')
    return reasons


def declared_diff_gaps(session: dict[str, Any]) -> list[str]:
    base = session['change'].get('baseRef')
    head = session['change'].get('headRef')
    if not base and not head:
        return []
    if not base or not head or base.startswith('-') or head.startswith('-'):
        return ['Review diff requires valid baseRef and headRef.']
    result = subprocess.run(
        [
            'git',
            'diff',
            '--name-only',
            '-z',
            '--no-ext-diff',
            f'{base}...{head}',
            '--',
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ['Review diff refs could not be resolved.']
    actual = {os.fsdecode(path) for path in result.stdout.split(b'\0') if path}
    missing = sorted(actual - set(session['changedFiles']))
    extra = sorted(set(session['changedFiles']) - actual)
    reasons = []
    if missing:
        reasons.append('Files missing from review diff: ' + ', '.join(missing))
    if extra:
        reasons.append('Files outside review diff: ' + ', '.join(extra))
    return reasons


def gate_issues(
    report: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    incomplete = []
    failed_blocking = []
    failed_advisory = []
    advisories = []
    gates = report['gates']
    if report['status'] != 'completed':
        incomplete.append('Gate report is not completed.')
    if not gates:
        incomplete.append('Gate report contains no executed gates.')
    elif not any(gate['blocking'] for gate in gates):
        incomplete.append('Gate report contains no blocking gate.')
    for gate in gates:
        status = gate['status']
        if gate['blocking']:
            if status == 'failed':
                failed_blocking.append(gate)
            elif status != 'passed' or gate['exitCode'] != 0:
                incomplete.append(
                    f'Blocking gate not verified: {gate["gateId"]}'
                )
        elif status in {'failed', 'external_failure'}:
            failed_advisory.append(gate)
        elif status != 'passed':
            advisories.append(f'Advisory gate not run: {gate["gateId"]}')
    return incomplete, failed_blocking, failed_advisory, advisories


def material_security_finding_ids(
    findings: list[dict[str, Any]],
) -> set[str]:
    return {
        finding['findingId']
        for finding in findings
        if finding['status'] != 'dismissed'
        and finding['topic'].casefold().startswith('security:')
        and finding['severity'] in {'blocker', 'warning'}
        and finding['confidence'] in {'high', 'medium'}
    }


def security_review_state(
    security: dict[str, Any] | None, findings: list[dict[str, Any]]
) -> tuple[str, bool, bool, list[str]]:
    security_ids = material_security_finding_ids(findings)
    missing = security_ids - (
        set(security['evidenceIds']) if security is not None else set()
    )
    required = bool(missing)
    outcome = 'not_requested'
    reasons = []
    if security_ids and security is None:
        outcome = 'handoff_required'
        reasons.append(
            'Material security finding requires a security handoff.'
        )
    elif missing:
        outcome = 'handoff_incomplete'
        reasons.append(
            'Security handoff omits material findings: '
            + ', '.join(sorted(missing))
        )
    if security is None:
        return outcome, required, False, reasons
    if security_ids and security['targetAgent'] != 'security-engineer':
        required = True
        reasons.append(
            'Material security findings require the security-engineer.'
        )
    if (
        security_ids
        and security['status'] in {'cleared', 'waived'}
        and (
            security.get('reviewedBy') != 'security-engineer'
            or not security.get('reviewSummary', '').strip()
        )
    ):
        required = True
        reasons.append(
            'Security review has no recorded specialist assessment.'
        )
    if not missing:
        outcome = security['status']
    if security['status'] in NON_TERMINAL_SECURITY_STATUSES:
        required = True
        reasons.append(f'Security review still open: {security["status"]}')
    changes_required = security['status'] == 'changes_required'
    if changes_required:
        reasons.append('Security engineer requested changes.')
    return outcome, required, changes_required, reasons


def evidence_gaps(
    session: dict[str, Any],
    gates: dict[str, Any],
    failed_blocking: list[dict[str, Any]],
    session_dir: Path,
) -> list[str]:
    if gates['status'] != 'completed':
        return []
    reasons = []
    if gates.get('reviewedFiles') != session['changedFiles']:
        reasons.append('Gate report covers a different set of changed files.')
    if not failed_blocking:
        issue = recorded_evidence_issue(gates, session_dir)
        if issue:
            reasons.append(issue)
    return reasons


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    plan = load_or_migrate_artifact(session_dir, 'review-plan')
    gates = load_or_migrate_artifact(session_dir, 'gate-report')
    verdict = load_or_migrate_artifact(session_dir, 'verdict')
    findings = list_findings(session_dir)

    security_path = session_dir / 'artifacts' / 'security-handoff.json'
    security = (
        load_or_migrate_artifact(session_dir, 'security-handoff')
        if security_path.exists()
        else None
    )
    for artifact in (plan, gates, verdict, security, *findings):
        if (
            artifact is not None
            and artifact['reviewId'] != session['reviewId']
        ):
            raise SystemExit('review artifacts belong to different sessions')

    incomplete_reasons = plan_gaps(session, plan)
    incomplete_reasons.extend(declared_diff_gaps(session))
    (
        gate_incomplete,
        failed_blocking_gates,
        failed_advisory_gates,
        gate_notes,
    ) = gate_issues(gates)
    incomplete_reasons.extend(gate_incomplete)
    incomplete_reasons.extend(
        evidence_gaps(session, gates, failed_blocking_gates, session_dir)
    )
    blocking_reasons: list[str] = []
    advisories: list[str] = gate_notes

    blocking_findings = [
        finding
        for finding in findings
        if (finding['blocking'] or finding['severity'] == 'blocker')
        and finding['status'] != 'dismissed'
    ]
    warning_findings = [
        finding
        for finding in findings
        if finding['severity'] == 'warning'
        and finding['status'] != 'dismissed'
    ]
    nit_findings = [
        finding
        for finding in findings
        if finding['severity'] == 'nit' and finding['status'] != 'dismissed'
    ]
    blocking_reasons.extend(
        f'{finding["findingId"]}: {finding["summary"]}'
        for finding in blocking_findings
    )
    advisories.extend(
        f'{finding["findingId"]}: {finding["summary"]}'
        for finding in warning_findings + nit_findings
    )

    blocking_reasons.extend(
        f'Blocking gate failed: {gate["gateId"]}'
        for gate in failed_blocking_gates
    )
    for gate in failed_advisory_gates:
        if gate['status'] == 'external_failure':
            advisories.append(f'Advisory gate unavailable: {gate["gateId"]}')
        else:
            advisories.append(f'Advisory gate failed: {gate["gateId"]}')

    (
        security_outcome,
        security_required,
        security_changes_required,
        security_reasons,
    ) = security_review_state(security, findings)
    blocking_reasons.extend(security_reasons)
    material_blockers = bool(blocking_reasons) and not security_required
    blocking_reasons.extend(incomplete_reasons)
    if security_changes_required:
        final_value = 'CHANGES_REQUIRED'
        summary = 'Security review requested changes.'
    elif security_required:
        final_value = 'SECURITY_REVIEW_REQUIRED'
        summary = 'Review is waiting for security review completion.'
    elif failed_blocking_gates:
        final_value = 'CHANGES_REQUIRED'
        summary = 'Review found failing blocking gates.'
    elif incomplete_reasons:
        final_value = 'INCOMPLETE'
        summary = 'Review lacks required evidence or completed review items.'
    elif material_blockers:
        final_value = 'CHANGES_REQUIRED'
        summary = 'Review found blocking issues.'
    elif advisories:
        final_value = 'APPROVED'
        summary = 'Review approved with advisory notes.'
    else:
        final_value = 'APPROVED'
        summary = 'Review approved with no blockers.'

    if verdict['status'] == 'draft':
        assert_transition('verdict', 'draft', 'final')
    verdict.update(
        {
            'artifactType': 'verdict',
            'schemaVersion': CURRENT_SCHEMA_VERSION,
            'reviewId': session['reviewId'],
            'status': 'final',
            'updatedAt': now_iso(),
            'verdict': final_value,
            'summary': summary,
            'blockingReasons': blocking_reasons,
            'advisories': advisories,
            'securityOutcome': security_outcome,
            'metrics': {
                'blockingFindings': len(blocking_findings),
                'warningFindings': len(warning_findings),
                'nitFindings': len(nit_findings),
                'failedBlockingGates': len(failed_blocking_gates),
                'failedAdvisoryGates': len(failed_advisory_gates),
            },
        },
    )
    save_artifact(session_dir, verdict)

    current_status = session['status']
    next_status = {
        'APPROVED': 'completed',
        'CHANGES_REQUIRED': 'completed',
        'SECURITY_REVIEW_REQUIRED': 'awaiting_security',
        'INCOMPLETE': 'blocked',
    }[final_value]
    if current_status != next_status:
        assert_transition('review-session', current_status, next_status)
        session['status'] = next_status
        session['updatedAt'] = now_iso()
        save_artifact(session_dir, session)
    update_session_statistics(session_dir)
    print(json.dumps(verdict, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
