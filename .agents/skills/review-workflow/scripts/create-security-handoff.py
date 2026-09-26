#!/usr/bin/env python3
"""Create or update a security review request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from runtime_support import (
    CURRENT_SCHEMA_VERSION,
    NON_TERMINAL_SECURITY_STATUSES,
    assert_transition,
    list_findings,
    load_or_migrate_artifact,
    now_iso,
    resolve_session_dir,
    save_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create or update a security review request.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument(
        '--status',
        choices=[
            'pending',
            'in_review',
            'cleared',
            'changes_required',
            'waived',
        ],
        default='pending',
    )
    parser.add_argument('--reason', required=True)
    parser.add_argument('--requested-by', default='review-workflow')
    parser.add_argument(
        '--target-agent',
        choices=['security-engineer'],
        default='security-engineer',
    )
    parser.add_argument('--reviewed-by', choices=['security-engineer'])
    parser.add_argument('--review-summary')
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--evidence-id', action='append', default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    gate_report = load_or_migrate_artifact(session_dir, 'gate-report')
    stamp = now_iso()
    if args.status in {'cleared', 'changes_required', 'waived'} and (
        args.reviewed_by != 'security-engineer'
        or not (args.review_summary or '').strip()
    ):
        raise SystemExit(
            'terminal security status requires --reviewed-by security-engineer '
            'and --review-summary from the specialist review'
        )

    handoff_path = session_dir / 'artifacts' / 'security-handoff.json'
    if handoff_path.exists():
        handoff = load_or_migrate_artifact(session_dir, 'security-handoff')
        if handoff['reviewId'] != session['reviewId']:
            raise SystemExit('security handoff belongs to another review')
        if handoff['status'] != args.status:
            assert_transition(
                'security-handoff', handoff['status'], args.status
            )
        handoff['updatedAt'] = stamp
    else:
        if args.status not in NON_TERMINAL_SECURITY_STATUSES:
            raise SystemExit(
                'create a pending security handoff before closing it'
            )
        handoff = {
            'artifactType': 'security-handoff',
            'schemaVersion': CURRENT_SCHEMA_VERSION,
            'reviewId': session['reviewId'],
            'status': args.status,
            'createdAt': stamp,
            'updatedAt': stamp,
            'targetAgent': args.target_agent,
            'requestedBy': args.requested_by,
            'reason': args.reason,
            'affectedFiles': [],
            'evidenceIds': [],
            'gateSummary': [],
            'reviewedBy': '',
            'reviewSummary': '',
        }

    all_findings = list_findings(session_dir)
    if any(item['reviewId'] != session['reviewId'] for item in all_findings):
        raise SystemExit('findings belong to another review')
    findings = {finding['findingId']: finding for finding in all_findings}
    evidence_ids = sorted(
        set(
            args.evidence_id
            or [
                item
                for item in findings
                if findings[item]['topic'].casefold().startswith('security:')
            ]
        )
    )
    if (
        handoff_path.exists()
        and handoff['status'] in {'cleared', 'changes_required', 'waived'}
        and args.status == handoff['status']
        and evidence_ids != handoff['evidenceIds']
    ):
        raise SystemExit('reopen the security handoff before adding findings')
    affected_files = sorted(
        set(
            args.file
            or [
                findings[item]['evidence']['file']
                for item in evidence_ids
                if item in findings
            ],
        ),
    )

    handoff['status'] = args.status
    handoff['reason'] = args.reason
    handoff['targetAgent'] = args.target_agent
    handoff['requestedBy'] = args.requested_by
    handoff['evidenceIds'] = evidence_ids
    handoff['affectedFiles'] = affected_files
    handoff['gateSummary'] = [
        f'{gate["gateId"]}={gate["status"]} '
        f'({"blocking" if gate["blocking"] else "advisory"})'
        for gate in gate_report['gates']
    ]
    handoff['reviewedBy'] = args.reviewed_by or ''
    handoff['reviewSummary'] = args.review_summary or ''
    save_artifact(session_dir, handoff)

    if args.status in NON_TERMINAL_SECURITY_STATUSES and session['status'] in {
        'reviewing',
        'apply-ready',
    }:
        assert_transition(
            'review-session', session['status'], 'awaiting_security'
        )
        session['status'] = 'awaiting_security'
        session['updatedAt'] = stamp
        save_artifact(session_dir, session)
    elif (
        args.status not in NON_TERMINAL_SECURITY_STATUSES
        and session['status'] == 'awaiting_security'
    ):
        assert_transition('review-session', 'awaiting_security', 'apply-ready')
        session['status'] = 'apply-ready'
        session['updatedAt'] = stamp
        save_artifact(session_dir, session)

    print(json.dumps(handoff, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
