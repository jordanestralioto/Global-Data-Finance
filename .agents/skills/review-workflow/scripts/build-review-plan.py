#!/usr/bin/env python3
"""Build a risk-ordered review plan."""

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
    assert_transition,
    build_plan_items,
    load_or_migrate_artifact,
    normalize_paths,
    now_iso,
    resolve_session_dir,
    save_artifact,
    update_session_statistics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Generate a risk-ordered review plan.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument('--changed-file', action='append', default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    plan = load_or_migrate_artifact(session_dir, 'review-plan')

    changed_files = normalize_paths(
        args.changed_file or session['changedFiles']
    )
    items = build_plan_items(changed_files, session['change']['securityTouch'])

    assert_transition('review-plan', plan['status'], 'ready')
    plan.update(
        {
            'schemaVersion': CURRENT_SCHEMA_VERSION,
            'status': 'ready',
            'updatedAt': now_iso(),
            'items': items,
        },
    )
    save_artifact(session_dir, plan)

    assert_transition('review-session', session['status'], 'planned')
    session['status'] = 'planned'
    session['updatedAt'] = now_iso()
    session['changedFiles'] = changed_files
    save_artifact(session_dir, session)
    update_session_statistics(session_dir)

    print(
        json.dumps(
            {
                'reviewId': session['reviewId'],
                'itemCount': len(items),
                'items': items,
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
