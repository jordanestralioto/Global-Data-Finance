#!/usr/bin/env python3
"""Portable test integrity checker to detect weakened, skipped, or deleted tests in git diff.

Detects common test erosion patterns:
  - Focused/isolated tests (.only, fit, fdescribe) - strictly prohibited
  - Skipped or xfailed tests (@pytest.mark.skip, it.skip, xit) - fail unless justified with reason
  - Unjustified net removal of assertion lines in test files
  - Deleted test files without staged policy authorization (.test-deletions.json)

Fail-closed: Exits with code 2 on git errors, code 1 on violations, code 0 on clean pass.
Zero external dependencies (Python 3.10+ standard library only).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class GitInspectionError(Exception):
    """Raised when a required Git inspection cannot be completed."""


# Focused tests are strictly prohibited in pre-commit (no bypass allowed)
STRICT_FOCUS_PATTERNS = [
    (
        re.compile(r'\b(?:it|describe|test)\.only\b'),
        'Focused test (.only) detected (strictly prohibited in pre-commit)',
    ),
    (
        re.compile(r'\b(?:fit|fdescribe)\('),
        'Focused test (fit/fdescribe) detected (strictly prohibited in pre-commit)',
    ),
]

# Skipped/xfailed tests fail by default, but can be permitted with explicit justification
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
    r'\b(?:assert\s+|expect\(|self\.assert|assert_that\b|t\.assert|assertIs|assertEqual|assertTrue|assertFalse)'
)

# Must include a colon and non-empty reason content
ALLOW_SKIP_RE = re.compile(
    r'(?:allow-skip|skip-reason):\s*\S+.*', re.IGNORECASE
)
ALLOW_ASSERTION_REDUCTION_RE = re.compile(
    r'(?:allow-assertion-reduction|assertion-reduction-reason):\s*\S+.*',
    re.IGNORECASE,
)


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


def _run_git(
    args: list[str], repo_root: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run Git and distinguish command failures from empty results."""
    try:
        return subprocess.run(
            ['git', *args],
            cwd=repo_root or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.SubprocessError,
        FileNotFoundError,
        OSError,
    ) as err:
        detail = getattr(err, 'stderr', None) or str(err)
        raise GitInspectionError(str(detail).strip()) from err


def read_staged_git_file(
    file_path: str, repo_root: Path | None = None
) -> str | None:
    """Read an indexed file, returning ``None`` only when it is absent."""
    root = repo_root or Path.cwd()
    index_entry = _run_git(['ls-files', '--stage', '--', file_path], root)
    if not index_entry.stdout.strip():
        return None
    return _run_git(['show', f':{file_path}'], root).stdout


def is_test_deletion_approved(
    file_path: str, repo_root: Path | None = None
) -> bool:
    """Check if test file deletion is registered in a staged policy file in git index."""
    policy_names = ('.test-deletions.json', '.test-integrity-policy.json')
    for policy_name in policy_names:
        content = read_staged_git_file(policy_name, repo_root)
        if content is not None:
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    allowed = data.get('allowed_deletions')
                    if isinstance(allowed, dict) and file_path in allowed:
                        reason = allowed[file_path]
                        if isinstance(reason, str) and reason.strip():
                            return True
                        if (
                            isinstance(reason, dict)
                            and str(reason.get('reason', '')).strip()
                        ):
                            return True
            except (OSError, json.JSONDecodeError):
                pass
    return False


def get_staged_diff(target_files: list[str] | None = None) -> str:
    """Retrieve staged git diff."""
    cmd = ['git', 'diff', '--cached', '--no-color', '-U1', '--']
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


def _evaluate_file_assertions(
    file_path: str,
    removed_assertions: int,
    added_assertions: int,
    has_reduction_allow: bool,
    is_deleted: bool,
    allow_deleted: bool,
    repo_root: Path | None = None,
) -> list[str]:
    """Evaluate whether changes to a test file violate integrity."""
    errors: list[str] = []
    if not (file_path and is_test_file(file_path)):
        return errors

    if is_deleted:
        if not (
            allow_deleted or is_test_deletion_approved(file_path, repo_root)
        ):
            errors.append(
                f'{file_path}: [TEST_DELETION] Test file deleted in staged changes. '
                'To authorize, pass --allow-deleted-tests or stage a policy entry in .test-deletions.json.'
            )
    elif removed_assertions > added_assertions and not has_reduction_allow:
        root = repo_root or Path.cwd()
        target_path = root / file_path
        if target_path.is_file():
            try:
                file_text = target_path.read_text(encoding='utf-8')
                if ALLOW_ASSERTION_REDUCTION_RE.search(file_text):
                    has_reduction_allow = True
            except OSError:
                pass
        if not has_reduction_allow:
            errors.append(
                f'{file_path}: [TEST_INTEGRITY] Net reduction of test assertions detected '
                f'({removed_assertions} removed vs {added_assertions} added without '
                f'"allow-assertion-reduction: <reason>")'
            )
    return errors


def _check_focus_or_skip_line(
    content: str, file_path: str, line_num: int
) -> list[str]:
    """Check an added line for focus or skip markers."""
    errors: list[str] = []
    # 1. Focused tests: strictly prohibited in pre-commit
    for pattern, desc in STRICT_FOCUS_PATTERNS:
        if pattern.search(content):
            errors.append(
                f'{file_path}:{line_num}: [TEST_FOCUS] {desc} ("{content}")'
            )

    # 2. Skipped/xfailed tests: fail by default unless explicitly justified with reason
    for pattern, desc in SKIPPED_TEST_PATTERNS:
        if pattern.search(content) and not ALLOW_SKIP_RE.search(content):
            errors.append(
                f'{file_path}:{line_num}: [TEST_SKIP] {desc} ("{content}")'
            )

    return errors


class _FileDiffState:
    """Track assertion and skip counts for a file during diff scanning."""

    def __init__(self) -> None:
        self.current_file: str = ''
        self.prev_file: str = ''
        self.line_num: int = 0
        self.removed_assertions: int = 0
        self.added_assertions: int = 0
        self.has_assertion_reduction_allow: bool = False
        self.is_deleted_file: bool = False

    def reset_for_file(self, file_path: str, is_deleted: bool = False) -> None:
        self.current_file = file_path
        self.removed_assertions = 0
        self.added_assertions = 0
        self.has_assertion_reduction_allow = False
        self.is_deleted_file = is_deleted

    def evaluate(
        self, allow_deleted: bool, repo_root: Path | None = None
    ) -> list[str]:
        return _evaluate_file_assertions(
            self.current_file,
            self.removed_assertions,
            self.added_assertions,
            self.has_assertion_reduction_allow,
            self.is_deleted_file,
            allow_deleted,
            repo_root,
        )


def scan_test_integrity(
    diff_text: str,
    allow_deleted_tests: bool = False,
    repo_root: Path | None = None,
) -> list[str]:
    """Scan diff for test integrity violations."""
    errors: list[str] = []
    state = _FileDiffState()

    for line in diff_text.splitlines():
        if line.startswith('--- a/'):
            state.prev_file = line[6:]
            continue

        if line.startswith('+++ b/'):
            errors.extend(state.evaluate(allow_deleted_tests, repo_root))
            state.reset_for_file(line[6:], is_deleted=False)
            continue

        if line.startswith('+++ /dev/null'):
            errors.extend(state.evaluate(allow_deleted_tests, repo_root))
            state.reset_for_file(state.prev_file, is_deleted=True)
            continue

        if not is_test_file(state.current_file):
            continue

        if line.startswith('@@ '):
            m = re.search(r'\+(\d+)', line)
            if m:
                state.line_num = int(m.group(1)) - 1
            continue

        if line.startswith('-') and not line.startswith('---'):
            if ASSERTION_PATTERNS.search(line[1:].strip()):
                state.removed_assertions += 1
            continue

        if line.startswith('+') and not line.startswith('+++'):
            state.line_num += 1
            content = line[1:].strip()
            if not content:
                continue
            if ALLOW_ASSERTION_REDUCTION_RE.search(content):
                state.has_assertion_reduction_allow = True
            if ASSERTION_PATTERNS.search(content):
                state.added_assertions += 1
            errors.extend(
                _check_focus_or_skip_line(
                    content, state.current_file, state.line_num
                )
            )

    errors.extend(state.evaluate(allow_deleted_tests, repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files',
        nargs='*',
        help='Specific files to check. If omitted, checks all staged test files.',
    )
    parser.add_argument(
        '--allow-deleted-tests',
        action='store_true',
        help='Allow test file deletions without failing the gate.',
    )
    args = parser.parse_args()

    try:
        diff_text = get_staged_diff(args.files if args.files else None)
        if not diff_text.strip():
            sys.stdout.write(
                'SKIP [TEST_INTEGRITY]: No staged test changes to inspect.\n'
            )
            return 0
        errors = scan_test_integrity(
            diff_text, allow_deleted_tests=args.allow_deleted_tests
        )
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [TEST_INTEGRITY]: unable to inspect staged Git changes: {err}\n'
        )
        return 2

    if errors:
        sys.stderr.write(
            'FAIL [TEST_INTEGRITY]: Test integrity violations detected in staged diff:\n'
        )
        for error_msg in errors:
            sys.stderr.write(f'  • {error_msg}\n')
        sys.stderr.write(
            '\nResolution: Restore assertions, remove .only/fit markers, or justify with '
            '"allow-assertion-reduction: <reason>" / "allow-skip: <reason>".\n'
        )
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
