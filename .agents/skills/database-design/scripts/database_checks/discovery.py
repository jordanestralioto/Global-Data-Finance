"""Find schema artifacts without importing a consumer's application stack."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

EXCLUDED_DIRS = {
    '.agents',
    '.claude',
    '.codex',
    '.opencode',
    '.git',
    '.hg',
    '.svn',
    '.venv',
    'venv',
    'node_modules',
    '__pycache__',
    'dist',
    'build',
    'vendor',
    'target',
    'bin',
    'obj',
}
SOURCE_SUFFIXES = {
    '.sql',
    '.prisma',
    '.py',
    '.ts',
    '.tsx',
    '.js',
    '.jsx',
    '.mjs',
    '.cjs',
    '.mts',
    '.cts',
    '.rb',
    '.go',
    '.php',
    '.java',
    '.kt',
    '.kts',
    '.cs',
    '.fs',
    '.rs',
    '.ex',
    '.exs',
    '.scala',
    '.clj',
    '.swift',
    '.dart',
}
ARTIFACT_DIRS = {'schema', 'schemas', 'models', 'migrations', 'drizzle'}


@dataclass
class Discovery:
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def matches(path: Path, patterns: list[str]) -> bool:
    return any(fnmatchcase(path.as_posix(), pattern) for pattern in patterns)


def conventional(path: Path) -> bool:
    stem = path.stem.lower()
    return path.suffix.lower() in SOURCE_SUFFIXES and (
        bool({part.lower() for part in path.parts[:-1]} & ARTIFACT_DIRS)
        or 'schema' in stem
        or 'migration' in stem
        or stem == 'models'
    )


def discover(
    paths: list[Path], includes: list[str], excludes: list[str]
) -> Discovery:
    result = Discovery()
    selected: set[Path] = set()
    for target in paths:
        if target.is_file():
            if not matches(Path(target.name), excludes):
                selected.add(target.resolve())
            continue
        if not target.is_dir():
            result.errors.append(
                f'Target is not a file or directory: {target}'
            )
            continue
        for directory, dirs, filenames in os.walk(
            target, onerror=lambda exc: result.errors.append(str(exc))
        ):
            base = Path(directory)
            dirs[:] = sorted(
                name
                for name in dirs
                if name not in EXCLUDED_DIRS
                and not (base / name).is_symlink()
                and not matches((base / name).relative_to(target), excludes)
            )
            for name in sorted(filenames):
                candidate = base / name
                relative = candidate.relative_to(target)
                if candidate.is_symlink() or matches(relative, excludes):
                    continue
                if conventional(relative) or matches(relative, includes):
                    selected.add(candidate.resolve())
    result.files = sorted(selected)
    return result
