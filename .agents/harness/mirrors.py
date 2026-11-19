"""Ownership-aware writes for the generated client mirrors.

The fan-out renders agents and workflows from the operated repository's
source root into client directories (``.claude/``, ``.codex/``, ``.github/``
and ``.opencode/``) and into the ``agent`` section of ``opencode.json``.
Those locations also hold content the repository owns, so the harness never
treats a whole directory as its own:

- an entry rendered from a current source is written whenever it differs;
- an entry of a source that the previous lock managed and that is no longer
  rendered is removed;
- every other entry is consumer-owned and is never read, reported or
  changed.

A component that the current lock manages but the previous lock did not may
have mirror targets the repository already uses. ``collisions`` lets
``projection.plan`` refuse the publish before anything is written unless
Git can restore every such target, the guard projected paths already use.
The generators repeat the guard on their own writes, so a standalone run is
protected too.

Mirrors of consumer-owned sources under ``.agents/`` are written while their
source exists. No lock records them, so removing that source leaves its
mirrors in place.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness import mirror_paths
from harness.consumer_types import parse_frontmatter, split_frontmatter
from harness.mirror_results import MirrorSync, conflict_message, report

__all__ = [
    'AGENT_MIRRORS',
    'CODEX_MIRROR',
    'LOCK_RELATIVE',
    'OPENCODE_CONFIG',
    'PREVIOUS_FLAG',
    'WORKFLOW_MIRRORS',
    'AgentSource',
    'Guard',
    'MirrorError',
    'MirrorSync',
    'Naming',
    'Ownership',
    'add_previous_argument',
    'agent_name',
    'claude_agent',
    'codex_agent',
    'collisions',
    'conflict_message',
    'describe',
    'lock_managed_paths',
    'ownership_for',
    'previous_flags',
    'read_agents',
    'read_json_object',
    'recoverable',
    'renamed',
    'report',
    'same_name',
    'source_names',
    'sync_files',
    'workflow_command',
]

LOCK_RELATIVE = Path('.agents') / 'harness.lock.json'
PREVIOUS_FLAG = '--previous-managed'
# A whole JSON string literal, or a comma that directly precedes a closing
# bracket. Strings match first, so a comma inside one is never removed.
STRING_OR_TRAILING_COMMA_RE = re.compile(
    r'"(?:[^"\\]|\\.)*"|,(?=\s*[\]}])', re.DOTALL
)

Guard = Callable[[Path, str], bool]
Naming = Callable[[str], str]


def agent_name(source_name: str) -> str:
    """The agent a ``<name>.agent.md`` source defines."""
    return source_name.removesuffix('.agent.md')


def claude_agent(source_name: str) -> str:
    return f'{agent_name(source_name)}.md'


def codex_agent(source_name: str) -> str:
    return f'{agent_name(source_name)}.toml'


def same_name(source_name: str) -> str:
    """GitHub agents and prompts keep the source file name."""
    return source_name


def workflow_command(source_name: str) -> str:
    """OpenCode and Claude commands drop the ``.prompt`` infix."""
    if source_name.endswith('.prompt.md'):
        return source_name.removesuffix('.prompt.md') + '.md'
    return source_name


# Mirror directory, relative to the repository root, and the target name of
# one source file in it.
AGENT_MIRRORS: tuple[tuple[str, Naming], ...] = (
    ('.claude/agents', claude_agent),
    ('.github/agents', same_name),
)
CODEX_MIRROR: tuple[str, Naming] = ('.codex/agents', codex_agent)
WORKFLOW_MIRRORS: tuple[tuple[str, Naming], ...] = (
    ('.github/prompts', same_name),
    ('.opencode/commands', workflow_command),
    ('.claude/commands', workflow_command),
)
OPENCODE_CONFIG = 'opencode.json'


class MirrorError(Exception):
    """A mirror source or target cannot be read safely."""


@dataclass(frozen=True)
class Ownership:
    """Source names whose mirrors the harness may remove or must guard."""

    removable: frozenset[str]
    guarded: frozenset[str]


@dataclass(frozen=True)
class AgentSource:
    """One agent definition as the mirror renderers consume it."""

    name: str
    metadata: dict[str, Any]
    body: str
    raw_frontmatter: str


def _path_list(value: str) -> tuple[str, ...]:
    try:
        paths = json.loads(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'not JSON: {exc}') from exc
    if not isinstance(paths, list) or not all(
        isinstance(path, str) for path in paths
    ):
        raise argparse.ArgumentTypeError('expected a JSON list of paths')
    return tuple(paths)


def add_previous_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        PREVIOUS_FLAG,
        type=_path_list,
        metavar='JSON',
        help=(
            'JSON list of the projection paths the previous lock managed; '
            'harness-sync always passes it, even empty, and a standalone '
            'run reads the current lock instead'
        ),
    )


def previous_flags(paths: Iterable[str] | None) -> list[str]:
    """Forward ``--previous-managed`` to another generator, if it was set."""
    if paths is None:
        return []
    return [f'{PREVIOUS_FLAG}={json.dumps(list(paths))}']


def lock_managed_paths(root: Path) -> frozenset[str]:
    """Paths the current lock manages; empty when it is absent or invalid."""
    try:
        payload = json.loads(
            (root / LOCK_RELATIVE).read_text(encoding='utf-8')
        )
    except (OSError, ValueError):
        return frozenset()
    managed = payload.get('managedPaths') if isinstance(payload, dict) else []
    if not isinstance(managed, list):
        return frozenset()
    return frozenset(item for item in managed if isinstance(item, str))


def source_names(managed: Iterable[str], kind: str) -> frozenset[str]:
    """Source file names directly under ``.agents/<kind>/`` in ``managed``."""
    prefix = f'.agents/{kind}/'
    names = (
        path.removeprefix(prefix)
        for path in managed
        if path.startswith(prefix)
    )
    return frozenset(name for name in names if name and '/' not in name)


def ownership_for(
    root: Path, previous: Iterable[str] | None, kind: str
) -> Ownership:
    """Split the managed sources of ``kind`` for one fan-out run.

    ``previous`` holds the paths the lock managed before the current
    publish. Without it, a standalone run treats the current lock as the
    previous one, so nothing is newly managed.
    """
    current = source_names(lock_managed_paths(root), kind)
    before = current if previous is None else source_names(previous, kind)
    return Ownership(removable=before, guarded=current - before)


def recoverable(root: Path, relative: str) -> bool:
    """Whether Git can restore ``relative``: tracked, unmodified, unignored."""
    try:
        mirror_paths.inspect(root, root / relative)
        completed = subprocess.run(
            [
                'git',
                'status',
                '--porcelain',
                '--untracked-files=all',
                '--ignored=matching',
                '--',
                relative,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, mirror_paths.UnsafePath):
        return False
    return completed.returncode == 0 and not completed.stdout.strip()


def describe(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def sync_files(
    root: Path,
    directory: Path,
    rendered: Mapping[str, str],
    ownership: Ownership,
    *,
    check: bool,
    guard: Guard = recoverable,
) -> MirrorSync:
    """Align the owned files of ``directory`` with ``rendered``.

    ``rendered`` maps target file names to their expected content, and
    ``ownership`` names targets, not sources. A file outside ``rendered``
    and ``ownership.removable`` is never touched.
    """
    result = MirrorSync()
    for name in sorted(set(rendered) | ownership.removable):
        path = directory / name
        relative = describe(path, root)
        try:
            if name in rendered:
                current = mirror_paths.read_text(root, path)
                if current == rendered[name]:
                    continue
                if (
                    current is not None
                    and name in ownership.guarded
                    and not check
                    and not guard(root, relative)
                ):
                    result.conflicts.append(relative)
                    continue
            elif not mirror_paths.is_file(root, path):
                continue
            result.stale.append(relative)
            if not check:
                if name in rendered:
                    mirror_paths.write_text(root, path, rendered[name])
                else:
                    mirror_paths.unlink(root, path)
                result.updated.append(relative)
        except mirror_paths.UnsafePath as exc:
            result.unsafe_paths[relative] = str(exc)
    return result


def renamed(ownership: Ownership, target: Callable[[str], str]) -> Ownership:
    """Map source names to the target names one mirror uses."""
    return Ownership(
        removable=frozenset(target(name) for name in ownership.removable),
        guarded=frozenset(target(name) for name in ownership.guarded),
    )


def read_agents(directory: Path) -> list[AgentSource]:
    """Parse every ``*.agent.md`` under ``directory``, sorted by file name."""
    agents: list[AgentSource] = []
    for path in sorted(directory.glob('*.agent.md')):
        text = path.read_text(encoding='utf-8')
        try:
            raw_frontmatter, _ = split_frontmatter(text)
            metadata, body = parse_frontmatter(text)
        except ValueError as exc:
            raise MirrorError(f'{path}: {exc}') from exc
        agents.append(
            AgentSource(
                name=path.name.removesuffix('.agent.md'),
                metadata=metadata,
                body=body.rstrip() + '\n',
                raw_frontmatter=raw_frontmatter,
            )
        )
    return agents


def read_json_object(
    path: Path, *, root: Path | None = None
) -> dict[str, Any]:
    """Read a JSON object, tolerating trailing commas outside strings."""
    text = mirror_paths.read_text(root or path.parent, path)
    if text is None:
        return {}
    cleaned = STRING_OR_TRAILING_COMMA_RE.sub(
        lambda match: match.group(0) if match.group(0) != ',' else '', text
    )
    try:
        payload = json.loads(cleaned)
    except ValueError as exc:
        raise MirrorError(f'{path}: invalid JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise MirrorError(f'{path}: expected a JSON object')
    return payload


def _opencode_agents(root: Path) -> dict[str, Any]:
    try:
        section = read_json_object(root / OPENCODE_CONFIG, root=root).get(
            'agent'
        )
    except MirrorError:
        return {}
    return section if isinstance(section, dict) else {}


def collisions(
    root: Path,
    managed: Iterable[str],
    previous: Iterable[str],
    *,
    guard: Guard = recoverable,
) -> list[str]:
    """Existing mirror entries of newly managed sources Git cannot restore."""
    newly = frozenset(managed) - frozenset(previous)
    targets = {
        'agents': (*AGENT_MIRRORS, CODEX_MIRROR),
        'workflows': WORKFLOW_MIRRORS,
    }
    found: list[str] = []
    for kind, entries in targets.items():
        for source in sorted(source_names(newly, kind)):
            for directory, target in entries:
                relative = f'{directory}/{target(source)}'
                try:
                    blocked = mirror_paths.is_file(
                        root, root / relative
                    ) and not guard(root, relative)
                except mirror_paths.UnsafePath:
                    blocked = True
                if blocked:
                    found.append(relative)
    if not source_names(newly, 'agents'):
        return found
    try:
        section = _opencode_agents(root)
    except mirror_paths.UnsafePath:
        return [*found, OPENCODE_CONFIG]
    claimed = [
        agent_name(source)
        for source in sorted(source_names(newly, 'agents'))
        if agent_name(source) in section
    ]
    if claimed and not guard(root, OPENCODE_CONFIG):
        found.extend(f'{OPENCODE_CONFIG}: agent {name}' for name in claimed)
    return found
