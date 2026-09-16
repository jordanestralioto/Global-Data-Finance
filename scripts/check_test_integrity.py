#!/usr/bin/env python3
"""Detect test erosion in staged or ranged Git diffs.

The gate rejects focused tests, skips, assertion loss, and stale policies.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.git_changes import GitInspectionError, get_diff, read_git_file
from scripts.integrity_policy import (
    file_patch_hashes,
    is_assertion_reduction_approved,
    is_test_deletion_approved,
    test_integrity_policy_errors,
)

# Focused tests are strictly prohibited in pre-commit (no bypass allowed)
STRICT_FOCUS_PATTERNS = [
    (
        re.compile(r'\b(?:it|describe|test)\.only\b'),
        'Focused test (.only) detected (strictly prohibited in pre-commit)',
    ),
    (
        re.compile(r'\b(?:fit|fdescribe)\('),
        'Focused test (fit/fdescribe) detected '
        '(strictly prohibited in pre-commit)',
    ),
]

SKIPPED_TEST_PATTERNS = [
    (
        re.compile(r'@pytest\.mark\.(?:skip|xfail)\b'),
        'Skipped/xfailed pytest marker added',
    ),
    (
        re.compile(r'\b(?:it|describe|test)\.skip\b'),
        'Skipped test (.skip) detected',
    ),
    (re.compile(r'\b(?:xit|xtest)\('), 'Skipped test (xit/xtest) detected'),
]

ASSERTION_PATTERNS = re.compile(
    r'\b(?:assert\s+|expect\(|self\.assert|assert_that\b|t\.assert|'
    r'assertIs|assertEqual|assertTrue|assertFalse|pytest\.(?:raises|warns)\()'
)

# Must include a colon and non-empty reason content.
ALLOW_SKIP_RE = re.compile(
    r'(?:allow-skip|skip-reason):\s*\S+.*', re.IGNORECASE
)
_ALLOW_DELETED_FLAG = '--allow-' + 'deleted-tests'


def is_test_file(file_path: str) -> bool:
    """Check if the given file path belongs to a test suite."""
    p = Path(file_path)
    name = p.name.lower()
    posix_path = p.as_posix().lower()
    return (
        name.startswith('test_')
        or name.endswith(
            (
                '_test.py',
                '.test.ts',
                '.test.js',
                '.test.tsx',
                '.test.jsx',
                '.spec.ts',
                '.spec.js',
                '.spec.tsx',
                '.spec.jsx',
            )
        )
        or '/tests/' in posix_path
        or '/__tests__/' in posix_path
        or posix_path.startswith(('tests/', 'test/'))
    )


def read_staged_git_file(
    file_path: str, repo_root: Path | None = None
) -> str | None:
    """Read an indexed file, returning ``None`` only when it is absent."""
    return read_git_file(file_path, repo_root=repo_root)


def get_staged_diff(target_files: list[str] | None = None) -> str:
    """Retrieve a non-renamed staged diff for direct script callers."""
    return get_diff(
        context_lines=1,
        target_files=target_files,
        no_renames=True,
    )


def _evaluate_file_assertions(
    file_path: str,
    removed_assertions: int,
    added_assertions: int,
    is_deleted: bool,
    allow_deleted: bool,
    diff_sha256: str | None,
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not (file_path and is_test_file(file_path)):
        return errors

    if is_deleted:
        if not (
            allow_deleted
            or is_test_deletion_approved(
                file_path,
                repo_root,
                revision_range,
            )
        ):
            errors.append(
                f'{file_path}: [TEST_DELETION] Test file deleted in staged '
                f'changes. To authorize, pass {_ALLOW_DELETED_FLAG} '
                'or stage a policy entry in .test-integrity-policy.json.'
            )
    elif (
        removed_assertions > added_assertions
        and not is_assertion_reduction_approved(
            file_path,
            diff_sha256,
            is_test_file,
            repo_root,
            revision_range,
        )
    ):
        errors.append(
            f'{file_path}: [TEST_INTEGRITY] Net reduction of test '
            f'assertions detected ({removed_assertions} removed vs '
            f'{added_assertions} added without '
            'a hash-bound allowed_assertion_reductions entry)'
        )
    return errors


def _check_focus_or_skip_line(
    content: str, file_path: str, line_num: int
) -> list[str]:
    errors: list[str] = []
    for pattern, desc in STRICT_FOCUS_PATTERNS:
        if pattern.search(content):
            errors.append(
                f'{file_path}:{line_num}: [TEST_FOCUS] {desc} ("{content}")'
            )

    for pattern, desc in SKIPPED_TEST_PATTERNS:
        if pattern.search(content) and not ALLOW_SKIP_RE.search(content):
            errors.append(
                f'{file_path}:{line_num}: [TEST_SKIP] {desc} ("{content}")'
            )

    return errors


class _FileDiffState:
    def __init__(self, patch_hashes: dict[str, str]) -> None:
        self.current_file: str = ''
        self.prev_file: str = ''
        self.line_num: int = 0
        self.removed_assertions: int = 0
        self.added_assertions: int = 0
        self.is_deleted_file: bool = False
        self.patch_hashes = patch_hashes
        self.reduced_paths: set[str] = set()

    def reset_for_file(self, file_path: str, is_deleted: bool = False) -> None:
        self.current_file = file_path
        self.removed_assertions = 0
        self.added_assertions = 0
        self.is_deleted_file = is_deleted

    def evaluate(
        self,
        allow_deleted: bool,
        repo_root: Path | None = None,
        revision_range: str | None = None,
    ) -> list[str]:
        if (
            not self.is_deleted_file
            and self.removed_assertions > self.added_assertions
        ):
            self.reduced_paths.add(self.current_file)
        return _evaluate_file_assertions(
            self.current_file,
            self.removed_assertions,
            self.added_assertions,
            self.is_deleted_file,
            allow_deleted,
            self.patch_hashes.get(self.current_file),
            repo_root,
            revision_range,
        )

    def track_previous_file(self, line: str) -> bool:
        if not line.startswith('--- a/'):
            return False
        self.prev_file = line[6:]
        return True

    def handle_file_start(
        self,
        line: str,
        allow_deleted: bool,
        repo_root: Path | None,
        revision_range: str | None,
    ) -> list[str] | None:
        if line.startswith('+++ b/'):
            errors = self.evaluate(allow_deleted, repo_root, revision_range)
            self.reset_for_file(line[6:], is_deleted=False)
            return errors
        if line.startswith('+++ /dev/null'):
            errors = self.evaluate(allow_deleted, repo_root, revision_range)
            self.reset_for_file(self.prev_file, is_deleted=True)
            return errors
        return None

    def handle_hunk(self, line: str) -> bool:
        if not line.startswith('@@ '):
            return False
        match = re.search(r'\+(\d+)', line)
        if match:
            self.line_num = int(match.group(1)) - 1
        return True

    def handle_removal(self, line: str) -> bool:
        if not line.startswith('-') or line.startswith('---'):
            return False
        if ASSERTION_PATTERNS.search(line[1:].strip()):
            self.removed_assertions += 1
        return True

    def handle_addition(self, line: str) -> list[str] | None:
        if not line.startswith('+') or line.startswith('+++'):
            return None
        self.line_num += 1
        content = line[1:].strip()
        if not content:
            return []
        if ASSERTION_PATTERNS.search(content):
            self.added_assertions += 1
        return _check_focus_or_skip_line(
            content, self.current_file, self.line_num
        )

    def inspect_test_line(self, line: str) -> list[str]:
        if self.handle_hunk(line) or self.handle_removal(line):
            return []
        return self.handle_addition(line) or []


def scan_test_integrity(
    diff_text: str,
    allow_deleted: bool = False,
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    """Scan diff for test integrity violations."""
    errors: list[str] = []
    state = _FileDiffState(file_patch_hashes(diff_text))

    for line in diff_text.splitlines():
        if state.track_previous_file(line):
            continue

        file_errors = state.handle_file_start(
            line, allow_deleted, repo_root, revision_range
        )
        if file_errors is not None:
            errors.extend(file_errors)
            continue

        if is_test_file(state.current_file):
            errors.extend(state.inspect_test_line(line))

    errors.extend(state.evaluate(allow_deleted, repo_root, revision_range))
    errors.extend(
        test_integrity_policy_errors(
            diff_text,
            state.reduced_paths,
            is_test_file,
            repo_root=repo_root,
            revision_range=revision_range,
        )
    )
    return errors


def main() -> int:
    """Validate that test changes retain required executable assertions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files',
        nargs='*',
        help=(
            'Specific files to check. If omitted, checks all staged test '
            'files.'
        ),
    )
    parser.add_argument(
        _ALLOW_DELETED_FLAG,
        dest='allow_deleted',
        action='store_true',
        help='Allow test file deletions without failing the gate.',
    )
    parser.add_argument(
        '--range',
        dest='revision_range',
        help=(
            'Inspect an explicit Git A..B or A...B range instead of the index.'
        ),
    )
    parser.add_argument(
        '--print-hash',
        action='store_true',
        help=(
            'Print canonical SHA-256 hashes for test-file patches without '
            'evaluating the integrity policy.'
        ),
    )
    args = parser.parse_args()
    if args.files and args.revision_range:
        parser.error('files cannot be combined with --range')

    try:
        diff_text = get_diff(
            context_lines=1,
            target_files=args.files if args.files else None,
            revision_range=args.revision_range,
            no_renames=True,
        )
        if not diff_text.strip():
            scope = 'revision range' if args.revision_range else 'staged test'
            sys.stdout.write(
                f'SKIP [TEST_INTEGRITY]: No {scope} changes to inspect.\n'
            )
            return 0
        if args.print_hash:
            for file_path, digest in sorted(
                file_patch_hashes(diff_text).items()
            ):
                if is_test_file(file_path):
                    sys.stdout.write(f'{file_path} {digest}\n')
            return 0
        errors = scan_test_integrity(
            diff_text,
            allow_deleted=args.allow_deleted,
            revision_range=args.revision_range,
        )
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [TEST_INTEGRITY]: unable to inspect Git changes: {err}\n'
        )
        return 2

    if errors:
        sys.stderr.write(
            'FAIL [TEST_INTEGRITY]: Test integrity violations detected in '
            'Git diff:\n'
        )
        for error_msg in errors:
            sys.stderr.write(f'  • {error_msg}\n')
        sys.stderr.write(
            '\nResolution: Restore assertions, remove .only/fit markers, or '
            'add a matching hash-bound entry to '
            'allowed_assertion_reductions or use the documented skip reason.\n'
        )
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
