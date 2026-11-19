"""Read hook blocks from the repository pre-commit configuration text."""

from __future__ import annotations

import re


def hook_block(content: str, hook_id: str) -> str:
    """Return one hook block from the YAML configuration."""
    match = re.search(
        rf'(?ms)^[ ]+- id: {re.escape(hook_id)}\n.*?(?=^[ ]+- id: |\Z)',
        content,
    )
    if match is None:
        raise AssertionError(f'Missing hook: {hook_id}')
    return match.group(0)


def hook_ids_in_order(content: str) -> list[str]:
    """Return every configured hook identifier in execution order."""
    return re.findall(r'(?m)^[ ]+- id: (\S+)$', content)


def hook_repository(content: str, hook_id: str) -> str:
    """Return the ``repo`` value of the section that declares a hook."""
    repository = ''
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('- repo:'):
            repository = stripped.removeprefix('- repo:').strip()
        elif stripped == f'- id: {hook_id}':
            return repository
    raise AssertionError(f'Missing hook: {hook_id}')
