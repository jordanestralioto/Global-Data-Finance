"""Conservative path hints for review planning, independent of verdict rules."""

from __future__ import annotations

import re
from pathlib import Path

PATH_HINTS = {
    'security': [
        'auth',
        'authentication',
        'authorization',
        'credential',
        'credentials',
        'permission',
        'permissions',
        'policy',
        'secret',
        'secrets',
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
        'migrations',
        'model',
        'models',
        'parquet',
        'query',
        'repository',
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


def detect_path_hints(file_path: str, security_touch: str) -> set[str]:
    lower = file_path.lower()
    words = set(
        re.findall(
            r'[a-z0-9]+',
            re.sub(r'([a-z])([A-Z])', r'\1_\2', file_path).lower(),
        )
    )
    file_packs = {
        pack
        for pack, tokens in PATH_HINTS.items()
        if words.intersection(tokens)
    }
    if (
        security_touch == 'yes'
        or Path(lower).name
        in {
            'dockerfile',
            'package.json',
            'pyproject.toml',
            'uv.lock',
            'package-lock.json',
            'pnpm-lock.yaml',
            'yarn.lock',
            'requirements.txt',
        }
        or lower.startswith('.github/workflows/')
    ):
        file_packs.add('security')
    if '/tests/' in lower or lower.startswith('tests/'):
        file_packs.add('tests')
    if lower.endswith(('.md', '.rst', '.txt')) or '/docs/' in lower:
        file_packs.add('docs')
    return file_packs or {'behavior'}
