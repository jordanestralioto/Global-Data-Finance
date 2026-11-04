"""Data-only schemas, registries, and identity helpers for evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from harness.consumer_validation import parse_and_validate_request

SNAPSHOT_VERSION = 'consumer-validation-snapshot-v1'
CHECK_SCHEMA_VERSION = 'consumer-validation-check-v1'
SNAPSHOT_FIELDS = (
    'snapshotVersion',
    'protocolVersion',
    'profile',
    'executorVersion',
    'requestIdentity',
    'effectiveScopes',
    'validators',
    'counts',
    'status',
    'exitCode',
    'stableContentIdentity',
)
CURRENT_PROTOCOL_VERSION = 'consumer-validation-v1'
CURRENT_PROFILE = 'consumer-isolated-v1'

SnapshotParser = Callable[[Any], Any]


@dataclass(frozen=True)
class CompatibilityEntry:
    """One exact protocol, profile, or snapshot compatibility entry."""

    status: str
    parser: SnapshotParser | None = None


def _is_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.startswith('/') or '\\' in value or ':' in value:
        return False
    path = PurePosixPath(value)
    return (
        value == str(path) and '..' not in path.parts and '' not in path.parts
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in '0123456789abcdef' for char in value)
    )


def _require_exact_keys(
    value: Mapping[str, Any], keys: tuple[str, ...]
) -> None:
    if set(value) != set(keys):
        missing = sorted(set(keys) - set(value))
        extra = sorted(set(value) - set(keys))
        raise ValueError(f'keys mismatch; missing={missing}, extra={extra}')


def _validate_item(item: Any) -> None:
    if not isinstance(item, dict):
        raise TypeError('effective scope item must be an object')
    _require_exact_keys(item, ('name', 'path', 'sha256'))
    if not isinstance(item['name'], str) or not item['name']:
        raise ValueError('effective scope item name must be non-empty')
    if not _is_relative_path(item['path']):
        raise ValueError('effective scope item path must be relative POSIX')
    if not _is_sha256(item['sha256']):
        raise ValueError('effective scope item sha256 must be lowercase hex')


def _validate_scope(scope: Any) -> None:
    if not isinstance(scope, dict):
        raise TypeError('effective scope must be an object')
    _require_exact_keys(
        scope,
        ('excludedItems', 'items', 'name', 'path', 'required', 'status'),
    )
    if scope['name'] not in ('skills', 'agents', 'workflows'):
        raise ValueError('effective scope has an unsupported name')
    if not _is_relative_path(scope['path']):
        raise ValueError('effective scope path must be relative POSIX')
    if not isinstance(scope['required'], bool):
        raise TypeError('effective scope required must be boolean')
    if scope['status'] not in ('passed', 'skipped'):
        raise ValueError('snapshot scope status must be passed or skipped')
    if scope['status'] == 'skipped' and scope['required']:
        raise ValueError('a required snapshot scope cannot be skipped')
    for field in ('items', 'excludedItems'):
        items = scope[field]
        if not isinstance(items, list):
            raise TypeError(f'effective scope {field} must be a list')
        for item in items:
            _validate_item(item)
        if items != sorted(items, key=lambda value: value['name']):
            raise ValueError(f'effective scope {field} must be sorted')


def _validate_scopes(scopes: Any) -> None:
    if not isinstance(scopes, list):
        raise TypeError('effectiveScopes must be a list')
    for scope in scopes:
        _validate_scope(scope)
    if scopes != sorted(scopes, key=lambda value: value['name']):
        raise ValueError('effectiveScopes must be sorted')


def _validate_validators(validators: Any) -> None:
    if not isinstance(validators, list):
        raise TypeError('validators must be a list')
    for validator in validators:
        if not isinstance(validator, dict):
            raise TypeError('validator must be an object')
        _require_exact_keys(validator, ('id', 'status'))
        if not isinstance(validator['id'], str) or not validator['id']:
            raise ValueError('validator id must be non-empty')
        if validator['status'] != 'passed':
            raise ValueError('snapshot validator status must be passed')
    if validators != sorted(validators, key=lambda value: value['id']):
        raise ValueError('validators must be sorted')


def _validate_counts(counts: Any, scopes: list[dict[str, Any]]) -> None:
    if not isinstance(counts, dict):
        raise TypeError('counts must be an object')
    count_keys = ('scopes', 'items', 'passed', 'failed', 'skipped', 'errors')
    _require_exact_keys(counts, count_keys)
    if any(
        type(counts[key]) is not int or counts[key] < 0 for key in count_keys
    ):
        raise ValueError('counts must contain non-negative integers')
    if counts['scopes'] != len(scopes):
        raise ValueError('counts.scopes does not match effectiveScopes')
    if counts['items'] != sum(len(scope['items']) for scope in scopes):
        raise ValueError('counts.items does not match effectiveScopes')
    if (
        counts['passed'] != counts['items']
        or counts['failed']
        or counts['errors']
    ):
        raise ValueError('a passing snapshot must contain only passed items')
    if counts['skipped'] != sum(
        scope['status'] == 'skipped' for scope in scopes
    ):
        raise ValueError('counts.skipped does not match effectiveScopes')


def _validate_snapshot_data(
    data: Any, *, validate_versions: bool
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TypeError('snapshot must be a JSON object')
    _require_exact_keys(data, SNAPSHOT_FIELDS)
    for field in (
        'snapshotVersion',
        'protocolVersion',
        'profile',
        'executorVersion',
    ):
        if not isinstance(data[field], str) or not data[field]:
            raise ValueError(f'{field} must be a non-empty string')
    if validate_versions:
        if data['snapshotVersion'] != SNAPSHOT_VERSION:
            raise ValueError(
                'snapshotVersion is not the current snapshot version'
            )
        if data['protocolVersion'] != CURRENT_PROTOCOL_VERSION:
            raise ValueError(
                'protocolVersion is not the current protocol version'
            )
        if data['profile'] != CURRENT_PROFILE:
            raise ValueError('profile is not the current validation profile')
    for field in ('requestIdentity', 'stableContentIdentity'):
        if not _is_sha256(data[field]):
            raise ValueError(f'{field} must be a lowercase SHA-256 digest')
    scopes = data['effectiveScopes']
    _validate_scopes(scopes)
    _validate_validators(data['validators'])
    _validate_counts(data['counts'], scopes)
    if (
        data['status'] != 'passed'
        or type(data['exitCode']) is not int
        or data['exitCode'] != 0
    ):
        raise ValueError('snapshot status and exitCode must be passed and 0')
    return data


def validate_snapshot_document(data: Any) -> dict[str, Any]:
    """Validate a current snapshot's closed data-only structure."""
    return _validate_snapshot_data(data, validate_versions=True)


def is_valid_snapshot_document(data: Any) -> bool:
    """Return whether data satisfies the data-only snapshot contract."""
    try:
        validate_snapshot_document(data)
    except (TypeError, ValueError):
        return False
    return True


def normalized_request(request_data: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical request object used for stable identity."""
    protocol, profile, scopes = parse_and_validate_request(request_data)
    normalized_scopes = [
        {
            'exclude': sorted(scopes[name].get('exclude', [])),
            'include': sorted(scopes[name].get('include', [])),
            'name': name,
            'path': scopes[name]['path'],
            'required': scopes[name]['required'],
        }
        for name in sorted(scopes)
    ]
    return {
        'profile': profile,
        'protocolVersion': protocol,
        'scopes': normalized_scopes,
    }


def request_identity(request_data: dict[str, Any]) -> str:
    """Hash the normalized request using the protocol's compact serializer."""
    payload = json.dumps(
        normalized_request(request_data),
        sort_keys=True,
        ensure_ascii=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def serialize_canonical(data: Mapping[str, Any]) -> bytes:
    """Serialize one evidence document with its required compact framing."""
    return (
        json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=True,
            indent=None,
            separators=(',', ':'),
        )
        + '\n'
    ).encode('utf-8')


def _current_snapshot_parser(data: Any) -> Any:
    return _validate_snapshot_data(data, validate_versions=False)


SNAPSHOT_COMPATIBILITY_REGISTRY: dict[str, Any] = {SNAPSHOT_VERSION: 'current'}
SNAPSHOT_DATA_PARSERS: dict[str, SnapshotParser] = {
    SNAPSHOT_VERSION: _current_snapshot_parser
}
PROTOCOL_COMPATIBILITY_REGISTRY: dict[str, Any] = {
    CURRENT_PROTOCOL_VERSION: 'current'
}
PROFILE_COMPATIBILITY_REGISTRY: dict[str, Any] = {CURRENT_PROFILE: 'current'}

# Short aliases keep the registry ownership discoverable to installed adapters.
SNAPSHOT_REGISTRY = SNAPSHOT_COMPATIBILITY_REGISTRY
PROTOCOL_REGISTRY = PROTOCOL_COMPATIBILITY_REGISTRY
PROFILE_REGISTRY = PROFILE_COMPATIBILITY_REGISTRY


@contextmanager
def override_compatibility_registries(
    *,
    snapshots: Mapping[str, Any] | None = None,
    protocols: Mapping[str, Any] | None = None,
    profiles: Mapping[str, Any] | None = None,
    snapshot_parsers: Mapping[str, SnapshotParser] | None = None,
) -> Iterator[None]:
    """Temporarily inject exact registry entries for unit tests only."""
    registries = (
        (SNAPSHOT_COMPATIBILITY_REGISTRY, snapshots),
        (PROTOCOL_COMPATIBILITY_REGISTRY, protocols),
        (PROFILE_COMPATIBILITY_REGISTRY, profiles),
    )
    originals = [dict(registry) for registry, _ in registries]
    original_parsers = dict(SNAPSHOT_DATA_PARSERS)
    try:
        for (registry, replacement), _original in zip(
            registries, originals, strict=True
        ):
            if replacement is not None:
                registry.clear()
                registry.update(replacement)
        if snapshot_parsers is not None:
            SNAPSHOT_DATA_PARSERS.clear()
            SNAPSHOT_DATA_PARSERS.update(snapshot_parsers)
        yield
    finally:
        for (registry, _replacement), original in zip(
            registries, originals, strict=True
        ):
            registry.clear()
            registry.update(original)
        SNAPSHOT_DATA_PARSERS.clear()
        SNAPSHOT_DATA_PARSERS.update(original_parsers)


temporary_registry_override = override_compatibility_registries
