#!/usr/bin/env python3
"""Detect changes that need security review."""

from __future__ import annotations

import json
import sys

SENSITIVE_TOKENS = (
    'auth',
    'permission',
    'policy',
    'rls',
    'token',
    'secret',
    'middleware',
    'upload',
    'session',
    'dangerous',
    'innerhtml',
)


def main() -> int:
    payload = json.load(sys.stdin)
    changed_files = payload.get('changedFiles', [])
    findings = payload.get('findings', [])

    matched_files = [
        file_path
        for file_path in changed_files
        if any(token in file_path.lower() for token in SENSITIVE_TOKENS)
    ]
    credible_findings = [
        finding['findingId']
        for finding in findings
        if finding.get('topic', '').casefold().startswith('security:')
        and finding.get('confidence') in {'high', 'medium'}
    ]
    security_touch = 'yes' if matched_files or credible_findings else 'no'
    print(
        json.dumps(
            {
                'securityTouch': security_touch,
                'matchedFiles': matched_files,
                'credibleFindings': credible_findings,
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
