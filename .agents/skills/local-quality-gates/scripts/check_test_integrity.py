#!/usr/bin/env python3
"""Portable test integrity checker to detect weakened, skipped, or deleted tests in git diff.

Detects common test erosion patterns:
  - Focused/isolated tests (.only, fit, fdescribe) - strictly prohibited
  - Skipped or xfailed tests (@pytest.mark.skip, it.skip, xit) - fail unless justified with reason
  - Unjustified net removal of assertion lines in test files
  - Deleted test files without staged policy authorization (.test-deletions.json)
  - Renames that drop test classification or default test discovery

Paths come from NUL-delimited staged metadata and each test file's patch is
read as bytes and split by hunk counts, so Git quoting, prefixes, carriage
returns, and patch-like content cannot change which file or line is checked.

Fail-closed: Exits with code 2 on git errors, code 1 on violations, code 0 on clean pass.
Zero external dependencies (Python 3.10+ standard library only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path, PurePosixPath


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
# Broad classification folds case; default discovery below does not.
TEST_NAME_RE = re.compile(
    r'(?:test_.*\.py|.*_test\.py|.*\.(?:test|spec)\.[cm]?[jt]sx?)$',
    re.IGNORECASE | re.DOTALL,
)
JS_TEST_NAME = r'.*\.(?:test|spec)\.[cm]?[jt]sx?'
# pytest's default norecursedirs plus __pycache__; Jest and Vitest skip only
# node_modules by default.
PYTEST_SKIPPED_DIRS = r'\..*|.*\.egg|_darcs|build|CVS|dist|node_modules|venv|\{arch\}|__pycache__'
HUNK_RE = re.compile(r'@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
DIFF_FLAGS = ['--no-color', '--find-renames', '--no-ext-diff', '--no-textconv']


def is_test_file(file_path: str) -> bool:
    """Check if the given file path belongs to a test suite."""
    p = Path(file_path)
    name = p.name.lower()
    posix_path = p.as_posix().lower()
    return (
        name.startswith('test_')
        or TEST_NAME_RE.fullmatch(name) is not None
        or '/tests/' in posix_path
        or '/__tests__/' in posix_path
        or posix_path.startswith(('tests/', 'test/'))
    )


def is_default_discovered(file_path: str, *, fold_case: bool = False) -> bool:
    """Match default pytest, Jest, and Vitest discovery on one platform.

    ``fold_case`` models Windows, where pytest's fnmatch ignores case in the
    name and in skipped directories but still requires the exact ``.py``.
    """
    path = PurePosixPath(file_path)
    case = 'i' if fold_case else ''
    if re.fullmatch(rf'(?{case}:test_.*|.*_test)\.py', path.name, re.DOTALL):
        skipped = PYTEST_SKIPPED_DIRS
    elif re.fullmatch(JS_TEST_NAME, path.name, re.DOTALL):
        skipped = 'node_modules'
    else:
        return False
    return not any(
        re.fullmatch(f'(?{case}:{skipped})', part, re.DOTALL)
        for part in path.parts[:-1]
    )


def _run_git(args: list[str], repo_root: Path | None = None) -> bytes:
    """Run Git as bytes so paths and line breaks reach the parser unchanged."""
    try:
        return subprocess.run(
            ['git', *args],
            cwd=repo_root or Path.cwd(),
            capture_output=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError) as err:
        detail = getattr(err, 'stderr', None) or str(err)
        if isinstance(detail, bytes):
            detail = detail.decode('utf-8', 'replace')
        raise GitInspectionError(str(detail).strip()) from err


def read_staged_git_file(
    file_path: str, repo_root: Path | None = None
) -> str | None:
    """Read an indexed file, returning ``None`` only when it is absent."""
    root = repo_root or Path.cwd()
    index_entry = _run_git(
        ['--literal-pathspecs', 'ls-files', '--stage', '--', file_path], root
    )
    if not index_entry.strip():
        return None
    return _run_git(['show', f':{file_path}'], root).decode('utf-8', 'replace')


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
            except json.JSONDecodeError as err:
                raise GitInspectionError(
                    f'staged {policy_name} is not valid JSON: {err}'
                ) from err
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
    return False


def get_staged_changes(
    repo_root: Path | None = None,
) -> list[tuple[str, str, str]]:
    """Return ``(status, old, new)`` from raw NUL-delimited staged metadata."""
    raw = _run_git(
        ['diff', '--cached', '--name-status', '-z', *DIFF_FLAGS, '--'],
        repo_root,
    )
    if raw and not raw.endswith(b'\0'):
        raise GitInspectionError('unterminated staged name-status output')
    fields = iter(raw.split(b'\0')[:-1])
    changes = []
    try:
        for status in fields:
            old = os.fsdecode(next(fields))
            paired = status[:1] in (b'R', b'C')
            new = os.fsdecode(next(fields)) if paired else old
            changes.append((status[:1].decode('ascii', 'replace'), old, new))
    except StopIteration as exc:
        raise GitInspectionError(
            'incomplete staged name-status record'
        ) from exc
    return changes


def get_selected_paths(files: list[str]) -> set[str] | None:
    """Resolve CLI pathspecs to staged paths; ``None`` means no filter."""
    if not files:
        return None
    raw = _run_git(
        ['diff', '--cached', '--name-only', '-z', '--no-renames', '--', *files]
    )
    return {os.fsdecode(path) for path in raw.split(b'\0') if path}


def get_file_patch(old: str, new: str, repo_root: Path | None = None) -> str:
    """Read one staged change as text, even when Git would call it binary."""
    paths = dict.fromkeys((old, new))
    command = ['--literal-pathspecs', 'diff', '--cached', '-U1', '--text']
    raw = _run_git([*command, *DIFF_FLAGS, '--', *paths], repo_root)
    return raw.decode('utf-8', 'replace')


def iter_hunk_lines(patch: str) -> Iterator[tuple[str, int, str]]:
    """Yield ``(sign, new_line, text)`` using hunk counts, never content."""
    lines = iter(patch.split('\n'))
    for header in lines:
        match = HUNK_RE.match(header)
        if match is None:
            continue
        old_left, new_line = int(match[1] or 1), int(match[2])
        new_left = int(match[3] or 1)
        while old_left > 0 or new_left > 0:
            line = next(lines, None)
            if line is None:
                return
            sign, text = line[:1], line[1:]
            if sign == '\\':  # "\ No newline at end of file"
                continue
            if sign in {'-', '+'}:
                yield sign, new_line, text
            if sign != '+':  # removed or context line
                old_left -= 1
            if sign != '-':  # added or context line
                new_left -= 1
                new_line += 1


def check_test_renames(
    renames: list[tuple[str, str]], repo_root: Path | None = None
) -> list[str]:
    """Require the old path's staged deletion approval when discovery is lost."""
    errors = []
    for old, new in renames:
        loses_discovery = any(
            is_default_discovered(old, fold_case=fold)
            and not is_default_discovered(new, fold_case=fold)
            for fold in (False, True)
        )
        if (
            is_test_file(old)
            and (not is_test_file(new) or loses_discovery)
            and not is_test_deletion_approved(old, repo_root)
        ):
            errors.append(
                f'{old}: [TEST_DELETION] Rename to {new} removes test discovery. '
                'Stage allowed_deletions for the old path with a reason in .test-deletions.json.'
            )
    return errors


def check_test_deletions(
    paths: list[str], repo_root: Path | None = None
) -> list[str]:
    """Require a staged policy reason for every deleted test file."""
    return [
        f'{path}: [TEST_DELETION] Test file deleted in staged changes. '
        'To authorize, stage a policy entry with a reason in .test-deletions.json.'
        for path in paths
        if is_test_file(path)
        and not is_test_deletion_approved(path, repo_root)
    ]


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


def scan_file_patch(
    file_path: str, patch: str, repo_root: Path | None = None
) -> list[str]:
    """Check one test file's patch for markers and a net assertion loss."""
    errors: list[str] = []
    removed = added = 0
    has_reduction_allow = False
    for sign, line_num, text in iter_hunk_lines(patch):
        content = text.strip()
        if sign == '-':
            removed += len(ASSERTION_PATTERNS.findall(content))
            continue
        if not content:
            continue
        if ALLOW_ASSERTION_REDUCTION_RE.search(content):
            has_reduction_allow = True
        added += len(ASSERTION_PATTERNS.findall(content))
        errors.extend(_check_focus_or_skip_line(content, file_path, line_num))

    if removed > added and not has_reduction_allow:
        file_text = read_staged_git_file(file_path, repo_root)
        if file_text is None or not ALLOW_ASSERTION_REDUCTION_RE.search(
            file_text
        ):
            errors.append(
                f'{file_path}: [TEST_INTEGRITY] Net reduction of test assertions detected '
                f'({removed} removed vs {added} added without '
                f'"allow-assertion-reduction: <reason>")'
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files',
        nargs='*',
        help='Files for content checks; deletion and rename policy always checks all staged paths.',
    )
    args = parser.parse_args()

    try:
        changes = get_staged_changes()
        selected = get_selected_paths(args.files)
        errors = check_test_renames(
            [(old, new) for status, old, new in changes if status == 'R']
        )
        errors.extend(
            check_test_deletions(
                [old for status, old, _ in changes if status == 'D']
            )
        )
        scoped = [
            (old, new)
            for status, old, new in changes
            if status != 'D'
            and (selected is None or not selected.isdisjoint((old, new)))
        ]
        for old, new in scoped:
            if is_test_file(new):
                errors.extend(scan_file_patch(new, get_file_patch(old, new)))
    except GitInspectionError as err:
        sys.stderr.write(
            f'ERROR [TEST_INTEGRITY]: unable to inspect staged Git changes: {err}\n'
        )
        return 2

    if not changes and not errors:
        sys.stdout.write(
            'SKIP [TEST_INTEGRITY]: No staged test changes to inspect.\n'
        )
        return 0

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
