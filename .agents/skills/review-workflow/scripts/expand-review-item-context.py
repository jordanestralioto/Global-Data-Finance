#!/usr/bin/env python3
"""Expand context for one review item."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from runtime_support import (
    load_or_migrate_artifact,
    now_iso,
    resolve_session_dir,
    save_artifact,
    validate_context_expansion,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Expand review item context with bounded files.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument('--item-id', required=True)
    parser.add_argument('--reason', required=True)
    parser.add_argument('--file', action='append', default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    plan = load_or_migrate_artifact(session_dir, 'review-plan')
    target = next(
        (item for item in plan['items'] if item['itemId'] == args.item_id),
        None,
    )
    if target is None:
        raise SystemExit(f'item not found: {args.item_id}')

    approved_files = validate_context_expansion(
        target['contextFiles'], args.file
    )
    expansion = {
        'reason': args.reason,
        'files': approved_files,
        'createdAt': now_iso(),
    }
    target['expansions'].append(expansion)
    target['contextFiles'] = sorted(
        set(target['contextFiles'] + approved_files)
    )
    plan['updatedAt'] = now_iso()
    save_artifact(session_dir, plan)
    print(json.dumps(expansion, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
