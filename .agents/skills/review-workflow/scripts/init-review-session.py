#!/usr/bin/env python3
"""Initialize a canonical review session."""

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
    build_default_verdict,
    build_empty_gate_report,
    build_empty_plan,
    ensure_session_layout,
    list_findings,
    load_or_migrate_artifact,
    make_review_id,
    normalize_paths,
    now_iso,
    resolve_session_dir,
    save_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Initialize a canonical review session.'
    )
    parser.add_argument('--review-id', default=None)
    parser.add_argument('--session-dir', default=None)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--change-type', default=None)
    parser.add_argument('--changed-by', default=None)
    parser.add_argument(
        '--security-touch', choices=['yes', 'no', 'auto'], default=None
    )
    parser.add_argument('--base-ref', default=None)
    parser.add_argument('--head-ref', default=None)
    parser.add_argument('--changed-file', action='append', default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resume:
        return resume_session(args)
    if not args.change_type or not args.changed_by:
        raise SystemExit('--change-type and --changed-by are required')
    review_id = args.review_id or make_review_id()
    session_dir = resolve_session_dir(
        review_id=review_id, session_dir=args.session_dir
    )
    if session_dir.exists() and any(session_dir.iterdir()):
        raise SystemExit('session already exists; use --resume to reopen it')
    ensure_session_layout(session_dir)

    changed_files = normalize_paths(args.changed_file)
    stamp = now_iso()
    session = {
        'artifactType': 'review-session',
        'schemaVersion': CURRENT_SCHEMA_VERSION,
        'reviewId': review_id,
        'status': 'initialized',
        'createdAt': stamp,
        'updatedAt': stamp,
        'change': {
            'changeType': args.change_type,
            'changedBy': args.changed_by,
            'securityTouch': args.security_touch or 'auto',
            'baseRef': args.base_ref,
            'headRef': args.head_ref,
        },
        'changedFiles': changed_files,
        'statistics': {
            'totalItems': 0,
            'completedItems': 0,
            'findingCount': 0,
            'blockingFindingCount': 0,
        },
    }

    save_artifact(session_dir, session)
    save_artifact(session_dir, build_empty_plan(review_id))
    save_artifact(session_dir, build_empty_gate_report(review_id))
    save_artifact(session_dir, build_default_verdict(review_id))

    print(
        json.dumps(
            {
                'reviewId': review_id,
                'sessionDir': str(session_dir),
                'changedFiles': changed_files,
                'status': 'initialized',
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


def resume_session(args: argparse.Namespace) -> int:
    if not args.session_dir and not args.review_id:
        raise SystemExit('--resume requires --session-dir or --review-id')
    if any(
        (
            args.change_type,
            args.changed_by,
            args.security_touch,
            args.base_ref,
            args.head_ref,
            args.changed_file,
        )
    ):
        raise SystemExit('--resume does not accept creation options')
    session_dir = resolve_session_dir(
        review_id=args.review_id, session_dir=args.session_dir
    )
    session = load_or_migrate_artifact(session_dir, 'review-session')
    if args.review_id and session['reviewId'] != args.review_id:
        raise SystemExit('review ID does not match the existing session')
    artifact_statuses: dict[str, str] = {}
    for artifact_type in ('review-plan', 'gate-report', 'verdict'):
        artifact = load_or_migrate_artifact(session_dir, artifact_type)
        if artifact['reviewId'] != session['reviewId']:
            raise SystemExit(f'{artifact_type} belongs to a different review')
        artifact_statuses[artifact_type] = artifact['status']
    if any(
        finding['reviewId'] != session['reviewId']
        for finding in list_findings(session_dir)
    ):
        raise SystemExit('findings belong to a different review')
    print(
        json.dumps(
            {
                'reviewId': session['reviewId'],
                'sessionDir': str(session_dir),
                'changedFiles': session['changedFiles'],
                'status': session['status'],
                'planStatus': artifact_statuses['review-plan'],
                'gateStatus': artifact_statuses['gate-report'],
                'verdictStatus': artifact_statuses['verdict'],
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
