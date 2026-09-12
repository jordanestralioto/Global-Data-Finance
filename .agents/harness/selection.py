"""Component selection, resolution, hashing and lock production.

This module is the reading and reasoning half of the importer. It loads the
shipped catalog and the consumer-owned manifest, resolves the transitive
closure of declared ``requires`` edges, hashes component content exactly as
design decision D14 specifies, builds the lock document as bytes, and
validates the ``managedPaths`` of a lock being read.

It never writes a file, never runs a subprocess, never prints, and never
inspects ``.agents`` beyond the two committed files it is handed as paths:
the manifest and the lock. ``harness/projection`` writes the lock bytes this
module returns, and the plan it produces is the only way destination facts
reach the lock document.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from harness.paths import HARNESS_ROOT

if TYPE_CHECKING:
    from harness.projection import Plan

MANIFEST_NAME = 'harness.json'
LOCK_NAME = 'harness.lock.json'
STAGING_DIR_NAME = '.harness-staging'

MANIFEST_LISTS = (
    'skills',
    'agents',
    'workflows',
    'review',
    'runtime',
    'tools',
)
INSTALLED_COMMANDS = frozenset(
    {'opsx', 'opsx-handoff', 'opsx-sync', 'sabatina'}
)
BASE_DIRS = frozenset({'harness'})
_SERIALIZE_KWARGS: dict[str, Any] = {
    'indent': 2,
    'sort_keys': True,
    'ensure_ascii': False,
}


class SelectionError(Exception):
    """The manifest, catalog or lock cannot be resolved; nothing publishes."""


def load_review_owner(path: Path | None = None) -> str | None:
    """Load the sole source of truth for the review-unit owner.

    The owner is either one live ``skills/<name>`` component or ``null`` when
    the review unit is retired.  A caller may provide a path so projected and
    fixture harnesses never depend on this module's installation root.
    """
    if path is None:
        path = HARNESS_ROOT / 'harness' / 'review-owner.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise SelectionError(f'review owner missing at {path}') from exc
    except json.JSONDecodeError as exc:
        raise SelectionError(f'{path}: {exc}') from exc

    if not isinstance(payload, dict):
        raise SelectionError(f'{path}: review owner must be a JSON object')
    if set(payload) != {'schemaVersion', 'owner'}:
        raise SelectionError(
            f'{path}: review owner must contain only "schemaVersion" and '
            '"owner"'
        )
    if (
        type(payload.get('schemaVersion')) is not int
        or payload['schemaVersion'] != 1
    ):
        raise SelectionError(f'{path}: "schemaVersion" must be 1')

    owner = payload.get('owner')
    if owner is None:
        return None
    if not isinstance(owner, str):
        raise SelectionError(f'{path}: "owner" must be a skill id or null')
    owner_path = PurePosixPath(owner)
    if (
        owner != str(owner_path)
        or owner_path.parts[:1] != ('skills',)
        or len(owner_path.parts) != 2
        or owner_path.parts[1] in ('', '.', '..')
        or '\\' in owner
        or ':' in owner
    ):
        raise SelectionError(
            f'{path}: "owner" must be a normalized skills/<name> id'
        )
    return owner


def review_owner_name(owner: str) -> str:
    """Return the bare name for a validated live review owner."""
    return owner.split('/', 1)[1]


def load_component_migrations(
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load the optional component migrations file."""
    if path is None:
        path = HARNESS_ROOT / 'harness' / 'component-migrations.json'
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise SelectionError(f'{path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise SelectionError(
            f'{path}: component migrations must be a JSON object'
        )
    if payload.get('schemaVersion') != 1:
        raise SelectionError(f'{path}: "schemaVersion" must be 1')
    migrations = payload.get('migrations')
    if not isinstance(migrations, list):
        raise SelectionError(f'{path}: "migrations" must be a list')
    records: dict[str, dict[str, Any]] = {}
    for item in migrations:
        if not isinstance(item, dict):
            raise SelectionError(f'{path}: migration entry must be an object')
        if not isinstance(comp_id := item.get('componentId'), str):
            raise SelectionError(
                f'{path}: migration entry missing "componentId"'
            )
        records[comp_id] = item
    return records


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    source: str
    requires: tuple[str, ...]
    has_scripts: bool


@dataclass(frozen=True)
class Manifest:
    version: str
    selection: frozenset[str]


@dataclass(frozen=True)
class Component:
    id: str
    source_ref: str
    source: Path
    requires: tuple[str, ...]
    has_scripts: bool
    selected_by: str
    hash: str

    @property
    def target_relative(self) -> str:
        return f'.agents/{self.source_ref}'


@dataclass(frozen=True)
class Resolution:
    components: tuple[Component, ...]


def serialize(payload: dict[str, Any]) -> bytes:
    """Serialize a JSON document exactly as D14 fixes the format."""
    return (json.dumps(payload, **_SERIALIZE_KWARGS) + '\n').encode('utf-8')


def _relative_path_violation(value: str) -> str | None:
    """Reject absolute, non-POSIX, non-normalized or escaping paths."""
    if not value or value != str(PurePosixPath(value)):
        return f'{value!r} is not a normalized relative POSIX path'
    if value.startswith('/') or '\\' in value or ':' in value:
        return f'{value!r} is not a relative POSIX path'
    parts = PurePosixPath(value).parts
    if not parts:
        return f'{value!r} has no path segment; it must name content'
    if '..' in parts:
        return f'{value!r} contains a parent-directory segment'
    return None


def load_catalog(path: Path | None = None) -> dict[str, CatalogEntry]:
    if path is None:
        path = HARNESS_ROOT / 'harness' / 'components.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise SelectionError(f'component catalog missing at {path}') from exc
    except json.JSONDecodeError as exc:
        raise SelectionError(f'{path}: {exc}') from exc
    raw_components = (
        payload.get('components') if isinstance(payload, dict) else None
    )
    if not isinstance(raw_components, dict):
        raise SelectionError(f'{path}: "components" must be an object')
    entries: dict[str, CatalogEntry] = {}
    for component_id, raw in raw_components.items():
        if not isinstance(raw, dict):
            raise SelectionError(
                f'{path}: entry {component_id} must be an object'
            )
        if not isinstance(source := raw.get('source'), str) or not source:
            raise SelectionError(f'{path}: entry {component_id} has no source')
        if (violation := _relative_path_violation(source)) is not None:
            raise SelectionError(
                f'{path}: entry {component_id} source {violation}'
            )
        requires = raw.get('requires', [])
        if not isinstance(requires, list) or not all(
            isinstance(item, str) for item in requires
        ):
            raise SelectionError(
                f'{path}: entry {component_id} "requires" must be a list'
            )
        entries[str(component_id)] = CatalogEntry(
            id=str(component_id),
            source=source,
            requires=tuple(requires),
            has_scripts=bool(raw.get('hasScripts')),
        )
    return entries


def _validate_manifest_lists(
    path: Path, raw_components: dict[object, object]
) -> None:
    for list_name in raw_components:
        if list_name not in MANIFEST_LISTS:
            raise SelectionError(f'{path}: unknown list {list_name!r}')
    for list_name in MANIFEST_LISTS:
        if list_name not in raw_components:
            raise SelectionError(
                f'{path}: components lacks the required list {list_name!r}'
            )


def load_manifest(path: Path) -> Manifest:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise SelectionError(f'manifest missing at {path}') from exc
    except json.JSONDecodeError as exc:
        raise SelectionError(f'{path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise SelectionError(f'{path}: manifest must be a JSON object')

    for key in payload:
        if key not in ('version', 'components'):
            msg = (
                'unknown key "profiles"; components are selected individually '
                'and no profile or bundle exists'
                if key == 'profiles'
                else f'unknown key {key!r}'
            )
            raise SelectionError(f'{path}: {msg}')

    version = payload.get('version')
    if not isinstance(version, str) or not version:
        raise SelectionError(f'{path}: "version" must be a string')

    raw_components = payload.get('components')
    if raw_components is None:
        raise SelectionError(f'{path}: "components" is missing')
    if not isinstance(raw_components, dict):
        raise SelectionError(f'{path}: "components" must be an object')

    _validate_manifest_lists(path, raw_components)

    catalog = load_catalog()
    review_owner = load_review_owner()
    migrations = load_component_migrations()
    selected: set[str] = set()
    for list_name in MANIFEST_LISTS:
        names = raw_components.get(list_name)
        if not isinstance(names, list) or not all(
            isinstance(item, str) for item in names
        ):
            raise SelectionError(f'{path}: {list_name!r} must be a list')
        for name in names:
            selected.add(
                _resolve_name(
                    path, catalog, list_name, name, review_owner, migrations
                )
            )
    return Manifest(version=version, selection=frozenset(selected))


def _resolve_name(
    manifest_path: Path,
    catalog: dict[str, CatalogEntry],
    list_name: str,
    name: str,
    review_owner: str | None,
    migrations: dict[str, dict[str, Any]] | None = None,
) -> str:
    if name in BASE_DIRS:
        raise SelectionError(
            f'{manifest_path}: {name!r} is a base directory, not a '
            'selectable component'
        )
    if list_name == 'review':
        if review_owner is None:
            raise SelectionError(
                f'{manifest_path}: review unit is retired; remove '
                f'{name!r} from "review" or use its shipped migration'
            )
        expected_name = review_owner_name(review_owner)
        if name != expected_name:
            raise SelectionError(
                f'{manifest_path}: "review" accepts only '
                f'"{expected_name}", not {name!r}'
            )
        return review_owner
    if list_name == 'tools' and name in INSTALLED_COMMANDS:
        raise SelectionError(
            f'{manifest_path}: {name!r} is installed unconditionally with '
            'the distribution and is not a selectable component'
        )
    component_id = f'{list_name}/{name}'
    if component_id not in catalog:
        if migrations is not None and component_id in migrations:
            rec = migrations[component_id]
            action, msg = rec.get('action'), rec.get('message', '')
            rep = f' -> {r}' if (r := rec.get('replacement')) else ''
            raise SelectionError(
                f'{manifest_path}: {component_id} is retired ({action}{rep}): {msg}'
            )
        raise SelectionError(
            f'{manifest_path}: unknown component {component_id}'
        )
    return component_id


def component_hash(source: Path) -> str:
    """Hash a component exactly as D14 specifies.

    Walk the source recursively, skip ``__pycache__`` directories and
    ``.pyc`` files, hash each remaining file, sort the ``(relative path,
    file hash)`` pairs by the UTF-8 bytes of the path, join them as one
    line of path and one line of hash per pair, and hash the result.
    """
    pairs: list[tuple[str, str]] = []
    if source.is_file():
        files = [source]
        root = source.parent
    else:
        files = sorted(path for path in source.rglob('*') if path.is_file())
        root = source
    for path in files:
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pairs.append((relative, digest))
    pairs.sort(key=lambda pair: pair[0].encode('utf-8'))
    joined = ''.join(f'{relative}\n{digest}\n' for relative, digest in pairs)
    return 'sha256:' + hashlib.sha256(joined.encode('utf-8')).hexdigest()


def resolve(
    manifest: Manifest, catalog: dict[str, CatalogEntry]
) -> Resolution:
    resolved: set[str] = set()
    pending = sorted(manifest.selection)
    while pending:
        component_id = pending.pop()
        if component_id in resolved:
            continue
        entry = catalog.get(component_id)
        if entry is None:
            raise SelectionError(f'unknown component {component_id}')
        resolved.add(component_id)
        for required in entry.requires:
            if required not in catalog:
                raise SelectionError(
                    f'{component_id}: requires unknown component {required}'
                )
            if required not in resolved:
                pending.append(required)

    components: list[Component] = []
    for component_id in sorted(resolved):
        entry = catalog[component_id]
        if component_id in manifest.selection:
            selected_by = 'manifest'
        else:
            requiring = sorted(
                parent
                for parent in resolved
                if component_id in catalog[parent].requires
            )
            selected_by = f'dependency:{requiring[0]}'
        violation = _relative_path_violation(entry.source)
        if violation is not None:
            raise SelectionError(f'{component_id}: source {violation}')
        source = HARNESS_ROOT / entry.source
        if not source.exists():
            raise SelectionError(
                f'{component_id}: source {entry.source} does not exist'
            )
        components.append(
            Component(
                id=component_id,
                source_ref=entry.source,
                source=source,
                requires=entry.requires,
                has_scripts=entry.has_scripts,
                selected_by=selected_by,
                hash=component_hash(source),
            )
        )
    return Resolution(components=tuple(components))


def build_lock(resolution: Resolution, version: str, plan: Plan) -> bytes:
    components = [
        {
            'hasScripts': component.has_scripts,
            'hash': component.hash,
            'id': component.id,
            'selectedBy': component.selected_by,
        }
        for component in sorted(
            resolution.components, key=lambda item: item.id
        )
    ]
    replacements = [
        {'component': item.component, 'path': item.path}
        for item in sorted(plan.replacements, key=lambda item: item.path)
    ]
    payload: dict[str, Any] = {
        'centralVersion': version,
        'components': components,
        'managedPaths': sorted(plan.managed_paths),
        'replacements': replacements,
    }
    return serialize(payload)


def _managed_authority(catalog: dict[str, CatalogEntry]) -> frozenset[str]:
    """Every path a legitimate lock may list as managed.

    A managed path is either a base directory or the projected target of a
    catalog source. Sources that would not validate are excluded, so a
    hand-built catalog cannot smuggle an escaping path into the authority.
    """
    targets = {
        f'.agents/{entry.source}'
        for entry in catalog.values()
        if _relative_path_violation(entry.source) is None
    }
    targets.update(f'.agents/{name}' for name in BASE_DIRS)
    with contextlib.suppress(OSError, ValueError, TypeError, KeyError):
        targets.update(
            f'.agents/{src}'
            for rec in load_component_migrations().values()
            if isinstance(src := rec.get('source'), str)
            and _relative_path_violation(src) is None
        )
    return frozenset(targets)


def _validate_managed_path_entry(
    entry: str, authority: frozenset[str]
) -> str | None:
    if entry.startswith('/') or '\\' in entry or ':' in entry:
        return f'{entry!r} is not a relative POSIX path'
    if entry != str(PurePosixPath(entry)):
        return f'{entry!r} is not a normalized path'
    parts = PurePosixPath(entry).parts
    if not parts or parts[0] != '.agents':
        return f'{entry!r} is not rooted at .agents'
    if '..' in parts:
        return f'{entry!r} contains a parent-directory segment'
    if len(parts) == 1:
        return f'{entry!r} is .agents itself'
    reserved = {
        f'.agents/{MANIFEST_NAME}',
        f'.agents/{LOCK_NAME}',
        f'.agents/{STAGING_DIR_NAME}',
    }
    if entry in reserved:
        return f'{entry!r} names importer metadata or its staging directory'
    if entry not in authority:
        return f'{entry!r} matches no catalog source and no base directory'
    return None


def validate_managed_paths(
    entries: object, catalog: dict[str, CatalogEntry]
) -> list[str]:
    """Validate every managed path of a lock being read.

    Returns the list of human-readable violations; empty means the entries
    may be used as deletion authority. The list must be sorted, every entry
    must be a normalized relative POSIX path strictly inside ``.agents``,
    and every entry must be derivable from the installed catalog — either a
    base directory or the projected target of a declared source — so a
    hand-edited lock cannot authorize the deletion of consumer state.
    """
    if not isinstance(entries, list):
        return ['managedPaths must be a list']
    errors: list[str] = []
    if entries != sorted(entries):
        errors.append('managedPaths must be sorted')
    authority = _managed_authority(catalog)
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str):
            errors.append(f'{entry!r} is not a string')
            continue
        violation = _validate_managed_path_entry(entry, authority)
        if violation is not None:
            errors.append(violation)
            continue
        if entry in seen:
            errors.append(f'{entry!r} appears more than once')
        seen.add(entry)
    return errors


def _sorted_violation(items: object, key_name: str, label: str) -> str | None:
    if not isinstance(items, list):
        return f'{label} must be a list'

    def key(item: object) -> str:
        return (
            str(item.get(key_name))
            if isinstance(item, dict) and item.get(key_name) is not None
            else ''
        )

    if items != sorted(items, key=key):
        return f'{label} must be sorted by {key_name}'
    return None


def read_lock(
    path: Path, catalog: dict[str, CatalogEntry] | None = None
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise SelectionError(f'lock missing at {path}') from exc
    except json.JSONDecodeError as exc:
        raise SelectionError(f'{path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise SelectionError(f'{path}: lock must be a JSON object')
    if catalog is None:
        catalog = load_catalog()
    violations = validate_managed_paths(payload.get('managedPaths'), catalog)
    if violations:
        raise SelectionError(
            f'{path}: invalid managedPaths: ' + '; '.join(violations)
        )
    for key_name, label in (
        ('id', 'components'),
        ('path', 'replacements'),
    ):
        violation = _sorted_violation(payload.get(label), key_name, label)
        if violation is not None:
            raise SelectionError(f'{path}: {violation}')
    return payload
