"""Pruned, deterministic discovery without a dependency on Git or a stack."""

from __future__ import annotations

import os
import re
from fnmatch import fnmatchcase
from pathlib import Path

EXCLUDED_PARTS = frozenset(
    {
        '.git',
        '.agents',
        '.claude',
        '.codex',
        '.opencode',
        '.venv',
        'venv',
        'node_modules',
        'vendor',
        'dist',
        'build',
        'target',
        'out',
        'bin',
        'obj',
        '__pycache__',
        '.next',
        '.nuxt',
        '.svelte-kit',
        'coverage',
        '.pytest_cache',
        '.mypy_cache',
        '.ruff_cache',
    }
)
SOURCE_SUFFIXES = frozenset(
    {
        '.py',
        '.pyi',
        '.ts',
        '.tsx',
        '.js',
        '.jsx',
        '.mjs',
        '.cjs',
        '.go',
        '.rs',
        '.rb',
        '.php',
        '.java',
        '.kt',
        '.kts',
        '.cs',
        '.fs',
        '.ex',
        '.exs',
        '.scala',
        '.swift',
        '.dart',
        '.clj',
        '.erl',
        '.lua',
    }
)
API_DIRECTORIES = frozenset(
    {
        'api',
        'apis',
        'routes',
        'routers',
        'controllers',
        'endpoints',
        'handlers',
        'actions',
    }
)
TOOL_SCRIPTS = Path(__file__).resolve().parents[1]


def matches_path(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatchcase(path, pattern)
        or (pattern.startswith('**/') and fnmatchcase(path, pattern[3:]))
        for pattern in patterns
    )


def is_openapi_path(path: Path) -> bool:
    return path.suffix.lower() in {'.json', '.yaml', '.yml'} and bool(
        re.search(r'openapi|swagger', path.name, re.I)
    )


def is_api_source(path: Path) -> bool:
    if path.suffix.lower() not in SOURCE_SUFFIXES:
        return False
    return bool(
        any(part.lower() in API_DIRECTORIES for part in path.parts[:-1])
        or re.search(
            r'(^|[_-])(api|routes?|routers?|endpoints?|handlers?|actions?)($|[_-])|Controller$|Api$',
            path.stem,
            re.I,
        )
    )


def discover_api_files(
    target: Path,
    includes: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
) -> list[Path]:
    """An explicit file bypasses name conventions, never a directory symlink."""
    if target.is_symlink():
        raise ValueError(
            'Symlink targets are not inspected; select the real path.'
        )
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise ValueError(f'Not a file or directory: {target}')
    convention_root = Path(target.resolve().name)
    found: list[Path] = []
    for directory, names, files in os.walk(
        target, followlinks=False, onerror=raise_walk_error
    ):
        base = Path(directory)
        names[:] = sorted(
            name
            for name in names
            if not excluded(base / name, target, excludes)
        )
        for name in sorted(files):
            path = base / name
            if excluded(path, target, excludes):
                continue
            relative = path.relative_to(target)
            selected = (
                matches_path(relative.as_posix(), includes)
                if includes
                else is_openapi_path(relative)
                or is_api_source(convention_root / relative)
            )
            if selected:
                found.append(path)
    return sorted(found)


def excluded(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    relative = path.relative_to(root)
    return (
        path.is_symlink()
        or any(part in EXCLUDED_PARTS for part in relative.parts)
        or path.resolve().is_relative_to(TOOL_SCRIPTS)
        or matches_path(relative.as_posix(), patterns)
        or matches_path(relative.as_posix() + '/', patterns)
    )


def raise_walk_error(error: OSError) -> None:
    raise error
