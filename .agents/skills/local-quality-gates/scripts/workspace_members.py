#!/usr/bin/env python3
"""Read and conservatively match workspace configuration from Git's index."""

from __future__ import annotations

import json
import re
import subprocess
from functools import cache
from pathlib import Path


class GitInspectionError(Exception):
    """Raised when an index or Git operation cannot be inspected."""


def _run_git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ['git', *args],
            cwd=root,
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


def _index_file_exists(file_path: str, root: Path) -> bool:
    result = _run_git(['ls-files', '--stage', '--', file_path], root)
    return bool(result.stdout.strip())


def read_staged_git_file(
    file_path: str, repo_root: Path | None = None
) -> str | None:
    """Read a file from the index, returning ``None`` when it is absent."""
    root = repo_root or Path.cwd()
    if not _index_file_exists(file_path, root):
        return None
    result = _run_git(['show', f':{file_path}'], root)
    return result.stdout


def get_workspace_config_content(
    config_name: str, root: Path | None = None
) -> str | None:
    """Return workspace configuration only when it exists in the index."""
    return read_staged_git_file(config_name, root)


def normalize_path(path_str: str) -> str:
    """Normalize a repository path without consulting the working tree."""
    value = str(path_str).replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value


def _quoted_values(value: str) -> list[str]:
    return re.findall(r"['\"]([^'\"]+)['\"]", value)


def _parse_pnpm_workspace(content: str) -> list[str]:
    patterns: list[str] = []
    in_packages = False
    for line in content.splitlines():
        without_comment = line.split('#', 1)[0]
        stripped = without_comment.strip()
        indent = len(without_comment) - len(without_comment.lstrip())
        if not in_packages:
            if not stripped.startswith('packages:'):
                continue
            inline = stripped.partition(':')[2].strip()
            if inline:
                patterns.extend(_quoted_values(inline))
                if not patterns and inline.startswith('['):
                    patterns.extend(
                        item.strip().strip('"\'')
                        for item in inline.strip('[]').split(',')
                        if item.strip()
                    )
                return patterns
            in_packages = True
            continue
        if indent == 0 and stripped and ':' in stripped:
            break
        if stripped.startswith('-'):
            item = stripped[1:].strip().strip('"\'')
            if item:
                patterns.append(item)
    return patterns


def _node_workspace_members(content: str) -> list[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    workspaces = data.get('workspaces')
    if isinstance(workspaces, list):
        return [item for item in workspaces if isinstance(item, str)]
    if isinstance(workspaces, dict):
        packages = workspaces.get('packages')
        if isinstance(packages, list):
            return [item for item in packages if isinstance(item, str)]
    return []


def _get_node_workspace_members(root: Path) -> list[str] | None:
    """Extract Node workspace patterns from the index."""
    pnpm_content = get_workspace_config_content('pnpm-workspace.yaml', root)
    if pnpm_content is not None:
        return _parse_pnpm_workspace(pnpm_content)

    package_content = get_workspace_config_content('package.json', root)
    if package_content is not None:
        return _node_workspace_members(package_content)
    return None


def _toml_workspace_members(
    root: Path, filename: str, section: str
) -> list[str] | None:
    content = get_workspace_config_content(filename, root)
    if content is None:
        return None

    in_section = False
    arrays: dict[str, list[str]] = {}
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].split('#', 1)[0].strip()
        if line.startswith('['):
            in_section = line == f'[{section}]'
            index += 1
            continue
        if in_section and '=' in line:
            key, _, value = line.partition('=')
            key = key.strip()
            if key in {'members', 'exclude'}:
                array_text = value
                while ']' not in array_text and index + 1 < len(lines):
                    index += 1
                    array_text += lines[index].split('#', 1)[0]
                if ']' in array_text:
                    arrays[key] = _quoted_values(array_text)
        index += 1

    members = arrays.get('members', [])
    excludes = [f'!{item}' for item in arrays.get('exclude', [])]
    return [*members, *excludes]


def _get_python_workspace_members(root: Path) -> list[str] | None:
    """Extract uv workspace patterns from the index."""
    return _toml_workspace_members(root, 'pyproject.toml', 'tool.uv.workspace')


def _get_cargo_workspace_members(root: Path) -> list[str] | None:
    """Extract Cargo workspace members and exclusions from the index."""
    return _toml_workspace_members(root, 'Cargo.toml', 'workspace')


def _get_go_workspace_members(root: Path) -> list[str] | None:
    """Extract Go workspace members from the indexed go.work file."""
    content = get_workspace_config_content('go.work', root)
    if content is None:
        return None

    members: list[str] = []
    in_use_block = False
    for line in content.splitlines():
        stripped = line.split('//', 1)[0].strip()
        if stripped.startswith('use ('):
            in_use_block = True
            continue
        if in_use_block:
            if stripped.startswith(')'):
                in_use_block = False
            elif stripped:
                members.append(stripped)
        elif stripped.startswith('use '):
            member = stripped[4:].strip()
            if member:
                members.append(member)
    return members


def _clean_pattern(raw_pattern: str) -> tuple[bool, tuple[str, ...]] | None:
    value = raw_pattern.strip().strip('"\'').strip()
    is_exclusion = value.startswith('!')
    if is_exclusion:
        value = value[1:].strip().strip('"\'').strip()
    if value.endswith('/...'):
        value = f'{value[:-4]}/**'
    elif value == '...':
        value = '**'
    while value.startswith('./'):
        value = value[2:]
    if (
        not value
        or value.startswith('/')
        or value.endswith('/')
        or '//' in value
        or '\\' in value
    ):
        return None

    segments = tuple(value.split('/'))
    if any(segment in {'.', '..', ''} for segment in segments):
        return None
    if any('**' in segment and segment != '**' for segment in segments):
        return None
    if any(any(char in segment for char in '[]{}') for segment in segments):
        return None
    return is_exclusion, segments


def _segment_matches(value: str, pattern: str) -> bool:
    expression: list[str] = ['^']
    for char in pattern:
        if char == '*':
            expression.append('[^/]*')
        elif char == '?':
            expression.append('[^/]')
        else:
            expression.append(re.escape(char))
    expression.append('$')
    return re.match(''.join(expression), value) is not None


def _path_matches_pattern(
    path_segments: tuple[str, ...], pattern_segments: tuple[str, ...]
) -> bool:
    @cache
    def matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_segments):
            return path_index == len(path_segments)
        pattern_segment = pattern_segments[pattern_index]
        if pattern_segment == '**':
            return matches(path_index, pattern_index + 1) or (
                path_index < len(path_segments)
                and matches(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_segments)
            and _segment_matches(path_segments[path_index], pattern_segment)
            and matches(path_index + 1, pattern_index + 1)
        )

    return matches(0, 0)


def _matches_any_member_pattern(
    dir_path: str, member_patterns: list[str]
) -> bool:
    """Match path segments, with any matching exclusion taking precedence."""
    clean_dir = normalize_path(dir_path).strip('/')
    if not clean_dir or clean_dir == '.':
        path_segments: tuple[str, ...] = ()
    elif clean_dir.startswith('/') or '..' in clean_dir.split('/'):
        return False
    else:
        path_segments = tuple(clean_dir.split('/'))

    included = False
    for raw_pattern in member_patterns:
        parsed = _clean_pattern(raw_pattern)
        if parsed is None:
            continue
        is_exclusion, pattern_segments = parsed
        if not _path_matches_pattern(path_segments, pattern_segments):
            continue
        if is_exclusion:
            return False
        included = True
    return included


def is_manifest_member_of_workspace(
    manifest_path: Path, manifest_name: str, root: Path
) -> bool:
    """Prove child-manifest membership using only indexed configuration."""
    manifest_dir = normalize_path(str(manifest_path.parent))
    if manifest_name == 'package.json':
        members = _get_node_workspace_members(root)
    elif manifest_name in ('pyproject.toml', 'requirements.in'):
        members = _get_python_workspace_members(root)
    elif manifest_name == 'Cargo.toml':
        members = _get_cargo_workspace_members(root)
    elif manifest_name == 'go.mod':
        members = _get_go_workspace_members(root)
    else:
        return False
    if not members:
        return False
    return _matches_any_member_pattern(manifest_dir, members)


def index_file_exists(file_path: str, root: Path | None = None) -> bool:
    """Return whether a path exists in the index; raise on Git failures."""
    return _index_file_exists(file_path, root or Path.cwd())
