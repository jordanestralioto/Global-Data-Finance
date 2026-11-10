"""Conservative path hints for review planning, independent of verdict rules."""

from __future__ import annotations

import re
from pathlib import Path

PATH_HINTS = {
    'security': [
        'auth',
        'oauth',
        'credential',
        'permission',
        'policy',
        'policies',
        'secret',
        'session',
        'token',
        'upload',
        'password',
        'crypto',
        'key',
        'keys',
        'jwt',
        'cors',
        'csrf',
        'rls',
        'middleware',
        'dangerous',
        'innerhtml',
    ],
    'interface': [
        'api',
        'cli',
        'contract',
        'controller',
        'endpoint',
        'handler',
        'interface',
        'route',
        'schema',
    ],
    'data': [
        'data',
        'db',
        'migration',
        'model',
        'parquet',
        'query',
        'queries',
        'repository',
        'repositories',
        'schema',
        'sql',
    ],
    'behavior': [
        'scripts',
        'src',
        'service',
        'core',
        'domain',
        'runtime',
        'worker',
        'lock',
    ],
}

# Tokens this long also match words that start with them, so plurals and
# derived names such as sessions, uploads or authenticate keep their hint.
# Shorter tokens such as key, api or db only match whole words.
PREFIX_MIN_LENGTH = 4

# Words that start with a hint token without carrying its meaning.
UNRELATED_WORDS = frozenset(
    {'author', 'authors', 'authored', 'authoring', 'authorship'}
)

SENSITIVE_FILE_NAMES = frozenset(
    {
        'dockerfile',
        'package.json',
        'pyproject.toml',
        'uv.lock',
        'package-lock.json',
        'pnpm-lock.yaml',
        'yarn.lock',
        'requirements.txt',
    }
)


def path_words(file_path: str) -> set[str]:
    """Split a path into lowercase words, including camelCase and acronyms."""
    spaced = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', file_path)
    spaced = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', spaced)
    return set(re.findall(r'[a-z0-9]+', spaced.lower()))


def word_matches(word: str, token: str) -> bool:
    if word == token:
        return True
    return (
        len(token) >= PREFIX_MIN_LENGTH
        and word.startswith(token)
        and word not in UNRELATED_WORDS
    )


def detect_path_hints(file_path: str, security_touch: str) -> set[str]:
    lower = file_path.lower()
    words = path_words(file_path)
    file_packs = {
        pack
        for pack, tokens in PATH_HINTS.items()
        if any(word_matches(word, token) for word in words for token in tokens)
    }
    if (
        security_touch == 'yes'
        or Path(lower).name in SENSITIVE_FILE_NAMES
        or lower.startswith('.github/workflows/')
    ):
        file_packs.add('security')
    if '/tests/' in lower or lower.startswith('tests/'):
        file_packs.add('tests')
    if lower.endswith(('.md', '.rst', '.txt')) or '/docs/' in lower:
        file_packs.add('docs')
    return file_packs or {'behavior'}
