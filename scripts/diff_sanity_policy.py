"""Line-level policies for the repository diff-sanity gate."""

from __future__ import annotations

import re
from pathlib import Path

_BREAKPOINT_WORD = 'breakpoint'
_DEBUGGER_WORD = 'debug' + 'ger'
_CONSOLE_WORD = 'console'
_PRINT_WORD = 'print'
_PRINT_CALL = _PRINT_WORD + '('
_TS_DIRECTIVE_PREFIX = '@' + 'ts-'
_IGNORE_WORD = 'ignore'
_NOCHECK_WORD = 'nocheck'
_EXPECT_ERROR_WORD = 'expect-error'

DEBUG_PATTERNS = [
    (
        re.compile(r'\b' + _BREAKPOINT_WORD + r'\(\)'),
        _BREAKPOINT_WORD + '() call detected',
        False,
    ),
    (
        re.compile(r'\b' + _DEBUGGER_WORD + r';?'),
        _DEBUGGER_WORD + ' statement detected',
        False,
    ),
    (
        re.compile(r'\b' + _CONSOLE_WORD + r'\.(?:log|debug|trace|dir)\('),
        _CONSOLE_WORD + '.log/debug statement detected',
        False,
    ),
    (
        re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(_PRINT_CALL)),
        'raw '
        + _PRINT_WORD
        + '() call detected (use logger or allow in configured files)',
        True,
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
        re.compile(r'#!?[\s]*(?:allow|expect)\s*\('),
        'Rust lint suppression attribute added',
    ),
    (
        re.compile(
            re.escape(_TS_DIRECTIVE_PREFIX)
            + r'(?:'
            + _IGNORE_WORD
            + '|'
            + _NOCHECK_WORD
            + '|'
            + _EXPECT_ERROR_WORD
            + r')\b'
        ),
        'TypeScript check bypass ('
        + _TS_DIRECTIVE_PREFIX
        + _IGNORE_WORD
        + '/'
        + _TS_DIRECTIVE_PREFIX
        + _NOCHECK_WORD
        + '/'
        + _TS_DIRECTIVE_PREFIX
        + _EXPECT_ERROR_WORD
        + ') added',
    ),
    (
        re.compile(r'#\s*type:\s*' + _IGNORE_WORD + r'\b'),
        'Python type check bypass (# type: ' + _IGNORE_WORD + ') added',
    ),
    (
        re.compile(r'(?://|/\*)\s*eslint-disable(?:-next-line|-line)?\b'),
        'ESLint bypass comment added',
    ),
]

NOQA_PATTERN = re.compile(r'#\s*noqa\b', re.IGNORECASE)
NOQA_LABEL = '# ' + 'noqa'
NOQA_DESCRIPTION = f'Linter bypass ({NOQA_LABEL}) is never permitted'

DOCUMENTATION_EXTENSIONS = frozenset({'.md', '.markdown', '.rst', '.txt'})
SECURITY_IGNORED_EXTENSIONS = frozenset(
    {
        '.gif',
        '.ico',
        '.jpeg',
        '.jpg',
        '.png',
        '.pdf',
        '.webp',
        '.woff',
        '.woff2',
        '.zip',
    }
)

_NO_VERIFY_FLAG = '--' + 'no-verify'
_TEST_DELETION_FLAG = '--allow-' + 'deleted-tests'
_TEST_DELETION_FILES_FLAG = '--allow-' + 'deleted-test-files'
_SKIP_ASSIGNMENT = 'SKIP' + '='
_HUSKY_ASSIGNMENT = 'HUSKY' + '=0'
_CONTINUE_ON_ERROR_KEY = 'continue-' + 'on-error'
_SHELL_PIPE_SUFFIX = '| ' + 'sh'
_SET_PLUS_E = 'set ' + '+e'

DANGEROUS_PATTERNS = [
    (
        re.compile(re.escape(_NO_VERIFY_FLAG) + r'\b'),
        f'Git {_NO_VERIFY_FLAG} hook bypass flag detected (prohibited)',
    ),
    (
        re.compile(
            r'(?i)(?:'
            + re.escape(_TEST_DELETION_FLAG)
            + r'\b|'
            + re.escape(_TEST_DELETION_FILES_FLAG)
            + r'\b|\ballow[_-]deleted[_-]tests?\b)'
        ),
        'Test-deletion integrity bypass flag detected (prohibited)',
    ),
    (
        re.compile(r'\b' + re.escape(_SKIP_ASSIGNMENT)),
        f'{_SKIP_ASSIGNMENT} environment hook bypass variable detected '
        '(prohibited)',
    ),
    (
        re.compile(r'\b' + re.escape(_HUSKY_ASSIGNMENT)),
        f'{_HUSKY_ASSIGNMENT} hook bypass variable detected (prohibited)',
    ),
    (
        re.compile(
            r'["\']?'
            + re.escape(_CONTINUE_ON_ERROR_KEY)
            + r'["\']?\s*:\s*true\b',
            re.IGNORECASE,
        ),
        f'{_CONTINUE_ON_ERROR_KEY} CI bypass detected (prohibited)',
    ),
    (
        re.compile(r'(?:curl|wget)\s+[^|]*\|\s*(?:ba)?sh\b'),
        f'Insecure curl {_SHELL_PIPE_SUFFIX} execution detected (prohibited)',
    ),
    (
        re.compile(r'\|\|\s*true\b'),
        'Shell OR true fallback bypass detected (prohibited)',
    ),
    (
        re.compile(r'\b' + re.escape(_SET_PLUS_E) + r'\b'),
        f'Shell error handling disabled with {_SET_PLUS_E} (prohibited)',
    ),
]

NON_INSPECTABLE_EXTENSIONS = frozenset(
    {
        *DOCUMENTATION_EXTENSIONS,
        '.json',
        '.yaml',
        '.yml',
        '.toml',
        '.lock',
        '.csv',
        '.tsv',
        '.xml',
        '.svg',
        '.png',
        '.jpg',
        '.jpeg',
        '.gif',
        '.ico',
        '.map',
    }
)


def is_inspectable_file(file_path: str) -> bool:
    """Determine if a file is an authored source/script file to be checked."""
    return Path(file_path).suffix.lower() not in NON_INSPECTABLE_EXTENSIONS


def is_bypass_inspectable_file(file_path: str) -> bool:
    """Return whether executable/configuration bypasses must be inspected."""
    suffix = Path(file_path).suffix.lower()
    return (
        suffix not in DOCUMENTATION_EXTENSIONS
        and suffix not in SECURITY_IGNORED_EXTENSIONS
    )


def is_security_inspectable_file(file_path: str) -> bool:
    """Return whether a file can contain text requiring safety inspection."""
    return Path(file_path).suffix.lower() not in SECURITY_IGNORED_EXTENSIONS


_DOCTEST_PREFIX = '>>>'


def check_debug_violations(
    content: str,
    file_path: str,
    line_num: int,
    allow_print_files: frozenset[str],
) -> list[str]:
    """Return debug violations, allowing output only in listed files."""
    errors: list[str] = []
    allow_print = file_path in allow_print_files
    is_doctest_line = content.startswith(_DOCTEST_PREFIX)
    for pattern, desc, is_print_pattern in DEBUG_PATTERNS:
        if is_print_pattern and (allow_print or is_doctest_line):
            continue
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [DEBUG] {desc}')
    return errors


def check_stub_violations(
    content: str, file_path: str, line_num: int
) -> list[str]:
    """Return stub and placeholder violations for one added line."""
    errors: list[str] = []
    for pattern, desc in STUB_PATTERNS:
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [STUB] {desc}')
    return errors


def check_bypass_violations(
    content: str, file_path: str, line_num: int
) -> list[str]:
    """Return compiler and linter bypass violations for one added line."""
    errors: list[str] = []
    for pattern, desc in BYPASS_PATTERNS:
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [BYPASS] {desc}')
    return errors


def check_noqa_violations(
    content: str, file_path: str, line_num: int
) -> list[str]:
    """Reject inline noqa independently of the other bypass policies."""
    if not NOQA_PATTERN.search(content):
        return []
    return [f'{file_path}:{line_num}: [BYPASS] {NOQA_DESCRIPTION}']


def check_security_violations(
    content: str,
    file_path: str,
    line_num: int,
    check_bypasses: bool,
) -> list[str]:
    """Apply executable bypass and universal operational policies."""
    errors: list[str] = []
    if is_bypass_inspectable_file(file_path):
        errors.extend(check_noqa_violations(content, file_path, line_num))
        if check_bypasses:
            errors.extend(
                check_bypass_violations(content, file_path, line_num)
            )
    for pattern, description in DANGEROUS_PATTERNS:
        if pattern.search(content):
            errors.append(f'{file_path}:{line_num}: [SECURITY] {description}')
    return errors
