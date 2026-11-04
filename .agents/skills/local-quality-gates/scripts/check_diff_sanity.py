#!/usr/bin/env python3
"""Portable sanity checker for git diffs to detect AI coding agent traps.

Detects common issues introduced on added/modified lines (+):
  - Leftover debug statements (console.log, breakpoint, debugger, raw print)
  - Stubbed implementations / unfulfilled placeholders (TODO throws, pass stubs)
  - Newly added type/lint bypasses in executable or configuration files
  - Operational hook and shell bypasses in every textual file

Documentation files may quote compiler/linter bypass markers as explanatory
content. Operational bypasses remain prohibited in documentation.

Fail-closed: Exits with code 2 on git errors, code 1 on violations, code 0 on clean pass.
Zero external dependencies (Python 3.10+ standard library only).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


class GitInspectionError(Exception):
    """Raised when git diff cannot be inspected."""


BREAKPOINT_LABEL = 'break' + 'point()'
DEBUGGER_LABEL = 'debug' + 'ger'
PRINT_LABEL = 'print' + '()'
TS_IGNORE_LABEL = '@ts-' + 'ignore'
TS_NOCHECK_LABEL = '@ts-' + 'nocheck'
TS_EXPECT_ERROR_LABEL = '@ts-' + 'expect-error'
PYTHON_TYPE_IGNORE_LABEL = '#' + ' type: ignore'

DEBUG_PATTERNS = [
    (
        re.compile(r'\b' + r'break' + r'point\(\)'),
        f'{BREAKPOINT_LABEL} call detected',
    ),
    (
        re.compile(r'\b' + r'debug' + r'ger;?'),
        f'{DEBUGGER_LABEL} statement detected',
    ),
    (
        re.compile(r'\bconsole\.(?:log|debug|trace|dir)\('),
        'console.log/debug statement detected',
    ),
    (
        re.compile(r'(?<![a-zA-Z0-9_])print\('),
        f'raw {PRINT_LABEL} call detected (use logger or allow in CLI files)',
    ),
]

STUB_PATTERNS = [
    (
        re.compile(r'throw\s+new\s+Error\(["\']TODO'),
        'TODO placeholder exception thrown',
    ),
    (
        re.compile(r'raise\s+NotImplementedError\(["\']TODO'),
        'TODO NotImplementedError thrown',
    ),
    (
        re.compile(r'pass\s*#\s*TODO', re.IGNORECASE),
        'pass TODO placeholder detected',
    ),
]

BYPASS_PATTERNS = [
    (
        re.compile(r'#!?\[\s*(?:allow|expect)\s*\('),
        'Rust lint suppression attribute added',
    ),
    (
        re.compile(r'@' + r'ts-(?:ignore|nocheck|expect-error)\b'),
        (
            'TypeScript check bypass ('
            f'{TS_IGNORE_LABEL}/{TS_NOCHECK_LABEL}/{TS_EXPECT_ERROR_LABEL}'
            ') added'
        ),
    ),
    (
        re.compile(r'#\s*' + r'type:\s*ignore\b'),
        f'Python type check bypass ({PYTHON_TYPE_IGNORE_LABEL}) added',
    ),
    (
        re.compile(r'(?://|/\*)\s*eslint-disable(?:-next-line|-line)?\b'),
        'ESLint bypass comment added',
    ),
]

DEBUG_ALLOW_RE = re.compile(r'allow-debug:\s*\S+.*', re.IGNORECASE)
STUB_ALLOW_RE = re.compile(
    r'(?:allow-stub|stub-reason|todo-reason):\s*\S+.*', re.IGNORECASE
)
NOQA_PATTERN = re.compile(r'#\s*noqa\b', re.IGNORECASE)
NOQA_DESCRIPTION = 'Linter bypass (noqa) is never permitted'

DOCUMENTATION_EXTENSIONS = frozenset({'.md', '.markdown', '.rst', '.txt'})
SECURITY_IGNORED_EXTENSIONS = frozenset(
    {'.gif', '.ico', '.jpeg', '.jpg', '.png', '.woff', '.woff2', '.zip'}
)

NO_VERIFY_FLAG = '--' + 'no-verify'
TEST_DELETION_FLAG = '--allow-' + 'deleted-tests'
TEST_DELETION_FILES_FLAG = '--allow-' + 'deleted-test-files'
SKIP_ASSIGNMENT = 'SKIP' + '='
CONTINUE_ON_ERROR_KEY = 'continue-' + 'on-error'
SHELL_PIPE_SUFFIX = '| ' + 'sh'
SHELL_PIPE_LABEL = 'curl ' + SHELL_PIPE_SUFFIX
SHELL_OR_TRUE_LABEL = 'shell OR true fallback'

DANGEROUS_PATTERNS = [
    (
        re.compile(re.escape(NO_VERIFY_FLAG) + r'\b'),
        f'Git {NO_VERIFY_FLAG} hook bypass flag detected (prohibited)',
    ),
    (
        re.compile(
            r'(?i)(?:'
            + re.escape(TEST_DELETION_FLAG)
            + r'\b|'
            + re.escape(TEST_DELETION_FILES_FLAG)
            + r'\b|\ballow[_-]deleted[_-]tests?\b)'
        ),
        'Test-deletion integrity bypass flag detected (prohibited)',
    ),
    (
        re.compile(r'\b' + re.escape(SKIP_ASSIGNMENT)),
        f'{SKIP_ASSIGNMENT} environment hook bypass variable detected (prohibited)',
    ),
    (
        re.compile(
            re.escape(CONTINUE_ON_ERROR_KEY) + r'\s*:\s*true\b',
            re.IGNORECASE,
        ),
        f'{CONTINUE_ON_ERROR_KEY} CI bypass detected (prohibited)',
    ),
    (
        re.compile(r'(?:curl|wget)\s+[^|]*\|\s*(?:ba)?sh\b'),
        f'Insecure {SHELL_PIPE_LABEL} execution detected (prohibited)',
    ),
    (
        re.compile(r'\|\|\s*true\b'),
        f'{SHELL_OR_TRUE_LABEL} bypass detected (prohibited)',
    ),
]

CONFIG_AND_ASSET_EXTENSIONS = frozenset(
    {'.csv', '.json', '.lock', '.map', '.svg'}
    | {'.toml', '.tsv', '.xml', '.yaml', '.yml'}
)
NON_INSPECTABLE_EXTENSIONS = (
    DOCUMENTATION_EXTENSIONS
    | SECURITY_IGNORED_EXTENSIONS
    | CONFIG_AND_ASSET_EXTENSIONS
) - frozenset({'.woff', '.woff2', '.zip'})


def is_inspectable_file(file_path: str) -> bool:
    """Determine if a file is an authored source/script file to be checked."""
    p = Path(file_path)
    return p.suffix.lower() not in NON_INSPECTABLE_EXTENSIONS


def is_bypass_inspectable_file(file_path: str) -> bool:
    suffix = Path(file_path).suffix.lower()
    return (
        suffix not in DOCUMENTATION_EXTENSIONS
        and suffix not in SECURITY_IGNORED_EXTENSIONS
    )


def is_security_inspectable_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() not in SECURITY_IGNORED_EXTENSIONS


def get_staged_diff(target_files: list[str] | None = None) -> str:
    """Retrieve staged git diff for specified files or all staged changes."""
    cmd = ['git', 'diff', '--cached', '--no-color', '-U0', '--']
    if target_files:
        cmd.extend(target_files)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout
    except (
        subprocess.CalledProcessError,
        subprocess.SubprocessError,
        FileNotFoundError,
    ) as err:
        raise GitInspectionError(str(err)) from err


def is_cli_or_script_file(file_path: str) -> bool:
    """Determine if file is a CLI entry point or script where print is expected."""
    p = Path(file_path)
    posix_path = p.as_posix().lower()
    return (
        '/cli/' in posix_path
        or '/scripts/' in posix_path
        or posix_path.startswith('scripts/')
        or p.name in ('manage.py', 'cli.py', 'main.py')
    )


def _check_debug_violations(
    content: str,
    file_path: str,
    line_num: int,
    allow_debug_in_scripts: bool,
    allow_print_files: frozenset[str],
) -> list[str]:
    errors: list[str] = []
    is_script = is_cli_or_script_file(file_path)
    allow_print = allow_debug_in_scripts and is_script
    allow_print = allow_print or file_path in allow_print_files
    for pattern, desc in DEBUG_PATTERNS:
        if 'print(' in desc and allow_print:
            continue
        if pattern.search(content) and not DEBUG_ALLOW_RE.search(content):
            errors.append(f'{file_path}:{line_num}: [DEBUG] {desc}')
    return errors


def _check_stub_violations(
    content: str, file_path: str, line_num: int
) -> list[str]:
    errors: list[str] = []
    for pattern, desc in STUB_PATTERNS:
        if pattern.search(content) and not STUB_ALLOW_RE.search(content):
            errors.append(f'{file_path}:{line_num}: [STUB] {desc}')
    return errors


def _check_bypass_violations(
    content: str, file_path: str, line_num: int
) -> list[str]:
    errors: list[str] = []
    for pattern, desc in BYPASS_PATTERNS:
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [BYPASS] {desc}')
    return errors


def _check_security_violations(
    content: str,
    file_path: str,
    line_num: int,
    check_bypasses: bool,
) -> list[str]:
    """Apply code-level bypass and universal operational policies."""
    errors: list[str] = []
    if is_bypass_inspectable_file(file_path):
        if NOQA_PATTERN.search(content):
            errors.append(
                f'{file_path}:{line_num}: [BYPASS] {NOQA_DESCRIPTION}'
            )
        if check_bypasses:
            errors.extend(
                _check_bypass_violations(content, file_path, line_num)
            )
    for pattern, desc in DANGEROUS_PATTERNS:
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [SECURITY] {desc}')
    return errors


def scan_diff(
    diff_text: str,
    allow_debug_in_scripts: bool = True,
    check_bypasses: bool = True,
    allow_print_files: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Scan added diff lines for violations and return formatted error messages."""
    errors: list[str] = []
    current_file = ''
    line_num = 0
    allowed_print_files = frozenset(allow_print_files or ())

    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            current_file = line[6:]
            continue
        if line.startswith('@@ '):
            m = re.search(r'\+(\d+)', line)
            if m:
                line_num = int(m.group(1)) - 1
            continue

        if not line.startswith('+') or line.startswith('+++'):
            continue

        if not is_security_inspectable_file(current_file):
            continue

        line_num += 1
        added_content = line[1:].strip()
        if not added_content:
            continue

        if is_inspectable_file(current_file):
            errors.extend(
                _check_debug_violations(
                    added_content,
                    current_file,
                    line_num,
                    allow_debug_in_scripts,
                    allowed_print_files,
                )
            )
            errors.extend(
                _check_stub_violations(added_content, current_file, line_num)
            )
        errors.extend(
            _check_security_violations(
                added_content,
                current_file,
                line_num,
                check_bypasses,
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files',
        nargs='*',
        help='Specific files to check. If omitted, checks all staged files.',
    )
    parser.add_argument(
        '--disallow-script-prints',
        action='store_true',
        help=f'Fail on {PRINT_LABEL} even inside scripts/ or cli/ directories.',
    )
    parser.add_argument(
        '--allow-print-file',
        action='append',
        default=[],
        metavar='PATH',
        help=(
            f'Allow {PRINT_LABEL} in this explicitly configured CLI path; repeat '
            'for each path.'
        ),
    )
    args = parser.parse_args()

    try:
        diff_text = get_staged_diff(args.files if args.files else None)
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [DIFF_SANITY]: unable to inspect staged Git changes: {err}\n'
        )
        return 2

    if not diff_text.strip():
        sys.stdout.write(
            'SKIP [DIFF_SANITY]: No staged diff additions to inspect.\n'
        )
        return 0

    errors = scan_diff(
        diff_text,
        allow_debug_in_scripts=not args.disallow_script_prints,
        check_bypasses=True,
        allow_print_files=frozenset(
            Path(path).as_posix() for path in args.allow_print_file
        ),
    )

    if errors:
        sys.stderr.write(
            'FAIL [DIFF_SANITY]: Potential AI agent artifacts detected in staged diff:\n'
        )
        for error_msg in errors:
            sys.stderr.write(f'  • {error_msg}\n')
        sys.stderr.write(
            '\nResolution: fix the code or document the behavior without '
            'executable suppressions; debug and stub exceptions require a '
            'specific reason.\n'
        )
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
