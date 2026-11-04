#!/usr/bin/env python3
"""Export a human-readable review summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[3] / 'runtime' / 'review')
)

from runtime_support import (
    list_findings,
    load_or_migrate_artifact,
    render_template,
    resolve_session_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Export a reproducible human-readable review summary.'
    )
    parser.add_argument('--session-dir', required=True)
    parser.add_argument('--output', default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(session_dir=args.session_dir)
    session = load_or_migrate_artifact(session_dir, 'review-session')
    plan = load_or_migrate_artifact(session_dir, 'review-plan')
    gates = load_or_migrate_artifact(session_dir, 'gate-report')
    verdict = load_or_migrate_artifact(session_dir, 'verdict')
    findings = list_findings(session_dir)

    summary = render_template(
        'review-summary.template.md',
        {
            'reviewId': session['reviewId'],
            'status': session['status'],
            'verdict': verdict['verdict'],
            'planProgress': (
                f'{session["statistics"]["completedItems"]}/'
                f'{session["statistics"]["totalItems"]}'
            ),
            'gateSummary': [
                f'- {gate["gateId"]}: {gate["status"]} '
                f'({"blocking" if gate["blocking"] else "advisory"})'
                for gate in gates['gates']
            ]
            or ['- nenhum gate executado'],
            'findings': [
                f'- {finding["findingId"]} '
                f'[{finding["severity"]}/{finding["confidence"]}]: '
                f'{finding["summary"]}'
                for finding in findings
            ]
            or ['- nenhum finding registrado'],
            'blockingReasons': [
                f'- {item}' for item in verdict['blockingReasons']
            ]
            or ['- nenhum bloqueio'],
            'changedFiles': [f'- {item}' for item in session['changedFiles']],
            'reviewItems': [
                f'- {item["itemId"]} · {item["topic"]} · {item["status"]}'
                for item in plan['items']
            ]
            or ['- nenhum item planejado'],
        },
    )

    output_path = session_dir / 'views' / 'review-summary.md'
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding='utf-8')

    print(
        json.dumps(
            {
                'reviewId': session['reviewId'],
                'outputPath': str(output_path),
                'verdict': verdict['verdict'],
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
