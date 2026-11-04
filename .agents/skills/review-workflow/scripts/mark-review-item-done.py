#!/usr/bin/env python3
"""Mark one review item as completed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from runtime_support import (
    assert_transition,
    load_or_migrate_artifact,
    now_iso,
    resolve_session_dir,
    save_artifact,
    update_session_statistics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Mark one review-plan item as completed.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument('--item-id', required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    plan = load_or_migrate_artifact(session_dir, 'review-plan')
    target = next(
        (item for item in plan['items'] if item['itemId'] == args.item_id),
        None,
    )
    if target is None:
        raise SystemExit(f'item not found: {args.item_id}')

    if plan['status'] == 'ready':
        assert_transition('review-plan', 'ready', 'in_review')
        plan['status'] = 'in_review'
    target['status'] = 'completed'
    plan['updatedAt'] = now_iso()
    if all(item['status'] == 'completed' for item in plan['items']):
        plan['status'] = 'completed'
    save_artifact(session_dir, plan)

    if session['status'] == 'planned':
        assert_transition('review-session', 'planned', 'reviewing')
        session['status'] = 'reviewing'
    if plan['status'] == 'completed' and session['status'] == 'reviewing':
        assert_transition('review-session', 'reviewing', 'apply-ready')
        session['status'] = 'apply-ready'
    session['updatedAt'] = now_iso()
    save_artifact(session_dir, session)
    update_session_statistics(session_dir)

    print(
        json.dumps(
            {
                'itemId': target['itemId'],
                'status': target['status'],
                'planStatus': plan['status'],
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
