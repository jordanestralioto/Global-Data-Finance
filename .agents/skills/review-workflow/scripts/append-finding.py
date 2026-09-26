#!/usr/bin/env python3
"""Append a canonical review finding."""

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
    load_or_migrate_artifact,
    normalize_repo_path,
    now_iso,
    resolve_session_dir,
    save_artifact,
    update_session_statistics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Persist a canonical review finding.'
    )
    parser.add_argument('--session-dir', required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.load(sys.stdin)
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    finding_id = (
        payload.get('findingId')
        or f'F-{session["statistics"]["findingCount"] + 1:03d}'
    )

    artifact = {
        'artifactType': 'finding',
        'schemaVersion': CURRENT_SCHEMA_VERSION,
        'reviewId': session['reviewId'],
        'findingId': finding_id,
        'status': payload.get('status', 'open'),
        'createdAt': payload.get('createdAt', now_iso()),
        'updatedAt': now_iso(),
        'topic': payload['topic'],
        'severity': payload['severity'],
        'confidence': payload['confidence'],
        'blocking': payload['severity'] == 'blocker'
        or bool(payload.get('blocking', False)),
        'summary': payload['summary'],
        'impact': payload['impact'],
        'recommendedAction': payload['recommendedAction'],
        'packId': payload.get('packId'),
        'checklistIds': payload.get('checklistIds', []),
        'evidence': {
            'file': normalize_repo_path(payload['evidence']['file']),
            'line': payload['evidence'].get('line'),
            'snippet': payload['evidence'].get('snippet', ''),
        },
    }

    save_artifact(session_dir, artifact)
    session['updatedAt'] = now_iso()
    if session['status'] == 'planned':
        session['status'] = 'reviewing'
    save_artifact(session_dir, session)
    update_session_statistics(session_dir)
    print(json.dumps({'findingId': finding_id}, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
