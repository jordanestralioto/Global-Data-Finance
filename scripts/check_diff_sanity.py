#!/usr/bin/env python3
"""Portable sanity checker for git diffs to detect AI coding agent traps.

Detects common issues introduced on added/modified lines (+) in the staged
index or an explicit Git revision range:
  - Leftover debug statements (console methods, pause calls, debug tokens)
  - Stubbed implementations / unfulfilled placeholders (TODO throws, pass)
  - Newly added type/lint bypass annotations in executable text
  - Operational hook and shell bypasses in every textual file

Documentation files may quote compiler/linter bypass markers as explanatory
content. Operational bypasses remain prohibited in documentation.

Fail-closed: Exits with code 2 on git errors, code 1 on violations, and code 0
on a clean pass.
Zero external dependencies (Python 3.10+ standard library only).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diff_sanity_policy import (
    NOQA_LABEL,
    check_debug_violations,
    check_security_violations,
    check_stub_violations,
    is_inspectable_file,
    is_security_inspectable_file,
)
from scripts.git_changes import (
    GitInspectionError,
    get_diff,
    is_external_harness_path,
)


def scan_diff(
    diff_text: str,
    check_bypasses: bool = True,
    allow_print_files: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Scan added diff lines and return formatted violation messages."""
    errors: list[str] = []
    current_file = ''
    line_num = 0
    allowed_print_files = frozenset(allow_print_files or ())

    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            current_file = line[6:]
            continue
        if line.startswith('@@ '):
            match = re.search(r'\+(\d+)', line)
            if match:
                line_num = int(match.group(1)) - 1
            continue

        if not line.startswith('+') or line.startswith('+++'):
            continue
        if is_external_harness_path(current_file):
            continue
        if not is_security_inspectable_file(current_file):
            continue

        line_num += 1
        added_content = line[1:].strip()
        if not added_content:
            continue

        if is_inspectable_file(current_file):
            errors.extend(
                check_debug_violations(
                    added_content,
                    current_file,
                    line_num,
                    allowed_print_files,
                )
            )
            errors.extend(
                check_stub_violations(added_content, current_file, line_num)
            )
        errors.extend(
            check_security_violations(
                added_content, current_file, line_num, check_bypasses
            )
        )

    return errors


def main() -> int:
    """Validate the current diff against repository safety rules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files',
        nargs='*',
        help='Specific files to check. If omitted, checks all staged files.',
    )
    parser.add_argument(
        '--allow-print-file',
        action='append',
        default=[],
        metavar='PATH',
        help=(
            'Allow explicit raw-output calls in this configured CLI path; '
            'repeat for each path.'
        ),
    )
    parser.add_argument(
        '--range',
        dest='revision_range',
        help=(
            'Inspect an explicit Git A..B or A...B range instead of the index.'
        ),
    )
    args = parser.parse_args()
    if args.files and args.revision_range:
        parser.error('files cannot be combined with --range')

    try:
        diff_text = get_diff(
            context_lines=0,
            target_files=args.files if args.files else None,
            revision_range=args.revision_range,
        )
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [DIFF_SANITY]: unable to inspect Git changes: {err}\n'
        )
        return 2

    if not diff_text.strip():
        scope = 'revision range' if args.revision_range else 'staged diff'
        sys.stdout.write(
            f'SKIP [DIFF_SANITY]: No {scope} additions to inspect.\n'
        )
        return 0

    errors = scan_diff(
        diff_text,
        check_bypasses=True,
        allow_print_files=frozenset(
            Path(path).as_posix() for path in args.allow_print_file
        ),
    )

    if errors:
        sys.stderr.write(
            'FAIL [DIFF_SANITY]: Potential AI agent artifacts detected in '
            'Git diff:\n'
        )
        for error_msg in errors:
            sys.stderr.write(f'  • {error_msg}\n')
        sys.stderr.write(
            '\nResolution: Fix the code, use the appropriate file/scope, or '
            'configure an explicit file-scoped output permission. '
            f'{NOQA_LABEL} and compiler/linter suppression annotations are '
            'never permitted.\n'
        )
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
