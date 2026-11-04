"""Executable-mode checks for files in a materialized harness projection."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from harness import selection
from harness.paths import HARNESS_ROOT

AGENTS_DIR_NAME = '.agents'
BASE_DIRS = ('harness',)


@dataclass(frozen=True)
class ExecutableModeDifference:
    relative_path: str
    source_executable: bool
    projected_executable: bool | None


def _ignored_entry(path: Path) -> bool:
    return (path.is_dir() and path.name == '__pycache__') or (
        path.is_file() and path.suffix == '.pyc'
    )


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _differences(
    source: Path,
    destination: Path,
    relative_path: str,
) -> tuple[ExecutableModeDifference, ...]:
    if source.is_file():
        source_executable = _is_executable(source)
        if not destination.is_file():
            return (
                ExecutableModeDifference(
                    relative_path,
                    source_executable,
                    None,
                ),
            )
        projected_executable = _is_executable(destination)
        if source_executable == projected_executable:
            return ()
        return (
            ExecutableModeDifference(
                relative_path,
                source_executable,
                projected_executable,
            ),
        )

    differences: list[ExecutableModeDifference] = []
    for child in sorted(source.iterdir()):
        if _ignored_entry(child):
            continue
        child_relative = (
            child.name
            if not relative_path
            else f'{relative_path}/{child.name}'
        )
        differences.extend(
            _differences(child, destination / child.name, child_relative)
        )
    return tuple(differences)


def executable_mode_differences(
    source: Path, destination: Path
) -> tuple[ExecutableModeDifference, ...]:
    """Return copied files whose executable behavior differs from source."""
    return _differences(source, destination, '')


def has_executable_mode_drift(
    resolution: selection.Resolution, repo_root: Path
) -> bool:
    base_drift = any(
        executable_mode_differences(
            HARNESS_ROOT / name,
            repo_root / AGENTS_DIR_NAME / name,
        )
        for name in BASE_DIRS
    )
    component_drift = any(
        executable_mode_differences(
            component.source, repo_root / component.target_relative
        )
        for component in resolution.components
    )
    return base_drift or component_drift


def _projected_path(target: str, relative_path: str) -> str:
    return target if not relative_path else f'{target}/{relative_path}'


def _difference_messages(
    subject: str,
    source: Path,
    destination: Path,
    target: str,
) -> list[str]:
    messages: list[str] = []
    for difference in executable_mode_differences(source, destination):
        path = _projected_path(target, difference.relative_path)
        if difference.projected_executable is None:
            messages.append(
                f'{subject}: {path} is missing from the projection'
            )
            continue
        expected = (
            'executable' if difference.source_executable else 'non-executable'
        )
        actual = (
            'executable'
            if difference.projected_executable
            else 'non-executable'
        )
        messages.append(
            f'{subject}: {path} executable mode drifted; '
            f'canonical {expected}, projected {actual}'
        )
    return messages


def executable_mode_drift_messages(
    resolution: selection.Resolution, repo_root: Path
) -> tuple[str, ...]:
    messages: list[str] = []
    for name in BASE_DIRS:
        target = f'{AGENTS_DIR_NAME}/{name}'
        destination = repo_root / target
        if not destination.exists():
            messages.append(f'{name}: {target} is missing from the projection')
            continue
        messages.extend(
            _difference_messages(
                name, HARNESS_ROOT / name, destination, target
            )
        )
    for component in resolution.components:
        destination = repo_root / component.target_relative
        if destination.exists():
            messages.extend(
                _difference_messages(
                    component.id,
                    component.source,
                    destination,
                    component.target_relative,
                )
            )
    return tuple(messages)
