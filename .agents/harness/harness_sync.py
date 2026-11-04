"""The ``harness-sync`` command: project, verify and update a selection.

A consuming repository commits ``.agents/harness.json`` and gets
``.agents`` materialized from the installed distribution plus generated client
links and the mirror fan-out. The surface is fixed: the default mode,
``--check``, ``--update`` and ``--list`` are mutually exclusive modes,
``--no-sync`` is the one modifier, and exit codes are 0 success, 1 drift or
failure, 2 usage error.

The pinned version is verified against the installed distribution and never
fetched; ``--update`` is the one operation that moves the pin. This module
is the only caller of the mirror generators, which run as subprocesses after
a successful publish.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from harness import client_links, projection, projection_modes, selection
from harness.paths import HARNESS_ROOT, repo_root

DISTRIBUTION_NAME = 'central-skills'
GENERATOR_SCRIPTS = (
    'sync-config-agents.py',
    'sync-workflows.py',
)


def _print(message: str = '') -> None:
    print(message)


def _error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def installed_version() -> str:
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as exc:
        raise selection.SelectionError(
            f'the central distribution {DISTRIBUTION_NAME!r} could not be '
            'found in this environment'
        ) from exc


def check_version(manifest: selection.Manifest) -> None:
    installed = installed_version()
    if manifest.version != installed:
        raise selection.SelectionError(
            f'the manifest pins central version {manifest.version} but the '
            f'installed distribution is {installed}; install '
            f'{manifest.version} or run `harness-sync --update` to adopt '
            f'{installed}'
        )


def resolve_and_plan(
    manifest: selection.Manifest,
    *,
    run_guard: bool = True,
) -> tuple[selection.Resolution, projection.Plan]:
    root = repo_root()
    catalog = selection.load_catalog()
    resolution = selection.resolve(manifest, catalog)
    plan = projection.plan(
        resolution, root, run_guard=run_guard, catalog=catalog
    )
    return resolution, plan


def _report_replacements(plan: projection.Plan) -> None:
    for replacement in plan.replacements:
        _print(f'replaced {replacement.path} with {replacement.component}')


def run_generator(script_name: str, root: Path) -> tuple[int, str]:
    script = HARNESS_ROOT / 'scripts' / script_name
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or '') + (completed.stderr or '')
    return completed.returncode, output


def run_fanout(root: Path) -> int:
    failures: list[str] = []
    try:
        client_links.synchronize(root)
    except client_links.ClientLinkError as exc:
        failures.append(f'client links failed:\n{exc}')
    for script_name in GENERATOR_SCRIPTS:
        returncode, output = run_generator(script_name, root)
        if returncode != 0:
            failures.append(f'{script_name} failed:\n{output.strip()}')
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    return 0


def _projection_matches(resolution: selection.Resolution, root: Path) -> bool:
    return projection.projection_content_matches(
        resolution, root
    ) and not projection_modes.has_executable_mode_drift(resolution, root)


def default_mode(no_sync: bool) -> int:
    root = repo_root()
    try:
        manifest = selection.load_manifest(
            root / '.agents' / selection.MANIFEST_NAME
        )
        check_version(manifest)
        resolution, plan = resolve_and_plan(manifest)
    except (selection.SelectionError, projection.ProjectionError) as exc:
        return _error(str(exc))
    lock_bytes = selection.build_lock(resolution, manifest.version, plan)
    lock_path = root / '.agents' / selection.LOCK_NAME
    if (
        lock_path.is_file()
        and lock_path.read_bytes() == lock_bytes
        and _projection_matches(resolution, root)
    ):
        pass
    else:
        try:
            projection.publish(resolution, plan, lock_bytes)
        except projection.ProjectionError as exc:
            return _error(str(exc))
        _report_replacements(plan)
    if no_sync:
        return 0
    return run_fanout(root)


def _lock_summary(old: dict[str, Any], new: bytes) -> list[str]:
    differences: list[str] = []
    raw_old_components = old.get('components')
    old_components = (
        raw_old_components if isinstance(raw_old_components, list) else []
    )
    new_payload = json.loads(new.decode('utf-8'))
    new_components = new_payload.get('components')
    if old_components != new_components:
        old_ids = {str(item['id']) for item in old_components}
        new_ids = {str(item['id']) for item in new_components}
        differences.extend(
            f'added component {component_id}'
            for component_id in sorted(new_ids - old_ids)
        )
        differences.extend(
            f'removed component {component_id}'
            for component_id in sorted(old_ids - new_ids)
        )
        differences.extend(
            f'changed component {component_id}'
            for component_id in sorted(old_ids & new_ids)
            if _entry(old_components, component_id)
            != _entry(new_components, component_id)
        )
    if old.get('managedPaths') != new_payload.get('managedPaths'):
        differences.append('managedPaths differ')
    if old.get('replacements') != new_payload.get('replacements'):
        differences.append('replacements differ')
    return differences


def _entry(
    components: list[dict[str, Any]], component_id: str
) -> dict[str, Any]:
    return next(item for item in components if item.get('id') == component_id)


def _base_targets() -> set[str]:
    return {f'.agents/{name}' for name in projection.BASE_DIRS}


def _component_targets(
    components: list[dict[str, Any]],
) -> dict[str, str]:
    return {
        str(item['id']): f'.agents/{_catalog_lookup(str(item["id"])).source}'
        for item in components
    }


def _catalog_lookup(component_id: str) -> selection.CatalogEntry:
    catalog = selection.load_catalog()
    entry = catalog.get(component_id)
    if entry is None:
        raise selection.SelectionError(f'unknown component {component_id}')
    return entry


def _check_against_lock(
    manifest: selection.Manifest,
    resolution: selection.Resolution,
    plan: projection.Plan,
    lock_path: Path,
) -> int:
    payload = selection.read_lock(lock_path)
    differences: list[str] = []

    new_bytes = selection.build_lock(resolution, manifest.version, plan)
    if lock_path.read_bytes() != new_bytes:
        differences.append('the lock differs from the resolved composition')
        differences.extend(_lock_summary(payload, new_bytes))

    managed_raw = payload.get('managedPaths')
    managed = set(managed_raw) if isinstance(managed_raw, list) else set()
    components_raw = payload.get('components')
    components = components_raw if isinstance(components_raw, list) else []
    base_targets = _base_targets()
    component_targets = _component_targets(components)
    known_targets = set(component_targets.values())
    differences.extend(
        f'{target} is managed but no lock component produces it'
        for target in sorted(managed - base_targets - known_targets)
    )
    differences.extend(
        f'{component_id} has a lock entry but {target} is not managed'
        for component_id, target in sorted(component_targets.items())
        if target not in managed
    )

    differences.extend(
        projection_modes.executable_mode_drift_messages(
            resolution, plan.repo_root
        )
    )

    recorded = {str(item['id']): item for item in components}
    for component in resolution.components:
        disk_path = plan.repo_root / component.target_relative
        lock_entry = recorded.get(component.id)
        if lock_entry is None:
            differences.append(
                f'{component.id} is resolved but absent from the lock'
            )
            continue
        if not disk_path.exists():
            differences.append(
                f'{component.id}: {component.target_relative} is missing '
                'from the projection'
            )
            continue
        recomputed = selection.component_hash(disk_path)
        if recomputed != lock_entry.get('hash'):
            differences.append(
                f'{component.id}: {component.target_relative} drifted; '
                f'recorded {lock_entry.get("hash")}, recomputed {recomputed}'
            )

    for difference in differences:
        print(difference, file=sys.stderr)
    return 1 if differences else 0


def check_mode() -> int:
    root = repo_root()
    try:
        manifest = selection.load_manifest(
            root / '.agents' / selection.MANIFEST_NAME
        )
        check_version(manifest)
        resolution, plan = resolve_and_plan(manifest, run_guard=False)
    except (selection.SelectionError, projection.ProjectionError) as exc:
        return _error(str(exc))
    lock_path = plan.repo_root / '.agents' / selection.LOCK_NAME
    if not lock_path.is_file():
        print('no lock: a first publish would materialize:', file=sys.stderr)
        for component in resolution.components:
            print(f'  {component.id}', file=sys.stderr)
        for replacement in plan.replacements:
            print(
                f'  replace {replacement.path} with {replacement.component}',
                file=sys.stderr,
            )
        return 1
    try:
        result = _check_against_lock(manifest, resolution, plan, lock_path)
    except selection.SelectionError as exc:
        return _error(str(exc))
    try:
        client_links.check(root)
    except client_links.ClientLinkError as exc:
        print(exc, file=sys.stderr)
        return 1
    return result


def _update_diff(
    old: dict[str, Any], resolution: selection.Resolution
) -> list[str]:
    lines: list[str] = []
    raw_old_components = old.get('components')
    old_components = (
        raw_old_components if isinstance(raw_old_components, list) else []
    )
    old_ids = {str(item['id']) for item in old_components}
    old_hash = {str(item['id']): item.get('hash') for item in old_components}
    new_ids = {component.id for component in resolution.components}
    new_hash = {
        component.id: component.hash for component in resolution.components
    }
    lines.extend(
        f'+ {component_id}' for component_id in sorted(new_ids - old_ids)
    )
    lines.extend(
        f'- {component_id}' for component_id in sorted(old_ids - new_ids)
    )
    lines.extend(
        f'~ {component_id}'
        for component_id in sorted(new_ids & old_ids)
        if old_hash[component_id] != new_hash[component_id]
    )
    return lines


def _rewrite_manifest_version(root: Path, version: str) -> None:
    manifest_path = root / '.agents' / selection.MANIFEST_NAME
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if payload.get('version') == version:
        return
    payload['version'] = version
    try:
        manifest_path.write_bytes(selection.serialize(payload))
    except OSError as exc:
        raise selection.SelectionError(
            f'could not write {version!r} into {manifest_path}: {exc}; '
            'the projection and lock are in place, re-running '
            '`harness-sync --update` completes the update'
        ) from exc


def update_mode(no_sync: bool) -> int:
    root = repo_root()
    try:
        manifest = selection.load_manifest(
            root / '.agents' / selection.MANIFEST_NAME
        )
        installed = installed_version()
        catalog = selection.load_catalog()
        resolution = selection.resolve(manifest, catalog)
        plan = projection.plan(resolution, root, catalog=catalog)
    except (selection.SelectionError, projection.ProjectionError) as exc:
        return _error(str(exc))

    lock_path = root / '.agents' / selection.LOCK_NAME
    if lock_path.is_file():
        old = selection.read_lock(lock_path, catalog)
    else:
        old = {'components': []}
    for line in _update_diff(old, resolution):
        _print(line)

    lock_bytes = selection.build_lock(resolution, installed, plan)
    try:
        projection.publish(resolution, plan, lock_bytes)
    except projection.ProjectionError as exc:
        return _error(str(exc))
    _report_replacements(plan)
    try:
        _rewrite_manifest_version(root, installed)
    except selection.SelectionError as exc:
        return _error(str(exc))
    if no_sync:
        return 0
    return run_fanout(root)


def list_mode() -> int:
    root = repo_root()
    try:
        manifest = selection.load_manifest(
            root / '.agents' / selection.MANIFEST_NAME
        )
        check_version(manifest)
        catalog = selection.load_catalog()
        resolution = selection.resolve(manifest, catalog)
    except selection.SelectionError as exc:
        return _error(str(exc))
    for component in resolution.components:
        mark = (
            'selected'
            if component.selected_by == 'manifest'
            else f'pulled by {component.selected_by.removeprefix("dependency:")}'
        )
        _print(f'{component.id}: {mark}')
    for component_id in sorted(catalog):
        if component_id not in {
            component.id for component in resolution.components
        }:
            _print(f'{component_id}: not selected')
    return 0


def _usage(message: str) -> int:
    print(f'usage error: {message}', file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='harness-sync',
        description=(
            'Materialize the harness selection from .agents/harness.json '
            'and regenerate client links, agent and workflow mirrors.'
        ),
    )
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--no-sync', action='store_true')
    args = parser.parse_args(argv)

    modes = [args.check, args.update, args.list]
    if sum(modes) > 1:
        return _usage('--check, --update and --list are mutually exclusive')
    if args.no_sync and (args.check or args.list):
        return _usage(
            '--no-sync is valid only with the default mode or --update'
        )

    if args.check:
        return check_mode()
    if args.update:
        return update_mode(no_sync=args.no_sync)
    if args.list:
        return list_mode()
    return default_mode(no_sync=args.no_sync)


if __name__ == '__main__':
    raise SystemExit(main())
