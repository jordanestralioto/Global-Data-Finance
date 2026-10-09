"""Read-only classification of isolated consumer validation snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.consumer_types import ContractError, Diagnostic
from harness.consumer_validation import verify_path_confinement
from harness.consumer_validation_evidence_schema import (
    CURRENT_PROFILE,
    CURRENT_PROTOCOL_VERSION,
    PROFILE_COMPATIBILITY_REGISTRY,
    PROTOCOL_COMPATIBILITY_REGISTRY,
    SNAPSHOT_COMPATIBILITY_REGISTRY,
    SNAPSHOT_DATA_PARSERS,
    SNAPSHOT_FIELDS,
    SNAPSHOT_VERSION,
    CompatibilityEntry,
    request_identity,
    serialize_canonical,
    validate_snapshot_document,
)

SNAPSHOT_RELATIVE_PATH = '.agents/validation/snapshot.json'
EVIDENCE_VALIDATOR_ID = 'consumer-validation.evidence'


class SnapshotReadError(ContractError):
    """The existing snapshot could not be read from the consumer root."""


@dataclass(frozen=True)
class SnapshotCheck:
    """The read-only classification of a consumer snapshot."""

    status: str
    diagnostics: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _InvalidDocument:
    message: str


def _diagnostic(code: str, message: str) -> dict[str, str]:
    return Diagnostic(
        SNAPSHOT_RELATIVE_PATH,
        EVIDENCE_VALIDATOR_ID,
        code,
        message,
    ).to_dict()


def snapshot_from_result(
    request_data: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Project a passing raw result into deterministic snapshot fields."""
    if result.get('status') != 'passed' or result.get('exitCode') != 0:
        raise ContractError('only a passing validation can publish a snapshot')
    scopes = [
        {
            'excludedItems': sorted(
                scope.get('excludedItems', []), key=lambda item: item['name']
            ),
            'items': sorted(scope['items'], key=lambda item: item['name']),
            'name': scope['name'],
            'path': scope['path'],
            'required': scope['required'],
            'status': scope['status'],
        }
        for scope in sorted(
            result['effectiveScopes'], key=lambda item: item['name']
        )
    ]
    snapshot = {
        'snapshotVersion': SNAPSHOT_VERSION,
        'protocolVersion': result['protocolVersion'],
        'profile': result['profile'],
        'executorVersion': result['executorVersion'],
        'requestIdentity': request_identity(request_data),
        'effectiveScopes': scopes,
        'validators': sorted(
            result['validators'], key=lambda item: item['id']
        ),
        'counts': {
            key: result['counts'][key] for key in sorted(result['counts'])
        },
        'status': 'passed',
        'exitCode': 0,
        'stableContentIdentity': result['stableContentIdentity'],
    }
    return validate_snapshot_document(snapshot)


def _entry(
    registry: Mapping[str, Any], version: Any
) -> CompatibilityEntry | None:
    if not isinstance(version, str) or not version:
        return None
    raw = registry.get(version)
    if isinstance(raw, CompatibilityEntry):
        return raw
    if isinstance(raw, str):
        return CompatibilityEntry(raw)
    if isinstance(raw, Mapping):
        status = raw.get('status')
        parser = raw.get('parser')
        if isinstance(status, str) and (parser is None or callable(parser)):
            return CompatibilityEntry(status, parser)
    return None


def _read_snapshot(root: Path) -> tuple[Any, bytes] | None:
    target = verify_path_confinement(
        root, SNAPSHOT_RELATIVE_PATH, 'snapshot path', must_exist=False
    )
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SnapshotReadError(
            f'cannot read {SNAPSHOT_RELATIVE_PATH}: {exc}'
        ) from exc
    try:
        candidate = json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return _InvalidDocument('snapshot is not valid UTF-8 JSON'), raw
    except json.JSONDecodeError:
        return _InvalidDocument('snapshot is not valid JSON'), raw
    except (RecursionError, ValueError):
        return (
            _InvalidDocument(
                'snapshot JSON exceeds the runtime parsing limits'
            ),
            raw,
        )
    return candidate, raw


def _version_diagnostic(field: str, value: Any) -> dict[str, str]:
    expected = {
        'snapshotVersion': SNAPSHOT_VERSION,
        'protocolVersion': CURRENT_PROTOCOL_VERSION,
        'profile': CURRENT_PROFILE,
    }.get(field, 'a registered value')
    return _diagnostic(
        'evidence.snapshot.invalid',
        f'{field} has unregistered or malformed value {value!r}; '
        f'expected current value {expected!r}',
    )


def _first_difference(
    expected: dict[str, Any], observed: dict[str, Any]
) -> tuple[str, Any, Any]:
    for field in SNAPSHOT_FIELDS:
        if expected.get(field) != observed.get(field):
            return field, expected.get(field), observed.get(field)
    return 'snapshot', expected, observed


def _canonical_snapshot(candidate: dict[str, Any]) -> bytes | None:
    """Return canonical bytes unless the document exceeds serializer limits."""
    try:
        return serialize_canonical(candidate)
    except (RecursionError, TypeError, ValueError):
        return None


def _canonical_issue(
    candidate: dict[str, Any], raw: bytes
) -> SnapshotCheck | None:
    """Return a closed invalid result for unsafe or non-canonical bytes."""
    canonical = _canonical_snapshot(candidate)
    if canonical is None:
        return SnapshotCheck(
            'invalid',
            (
                _diagnostic(
                    'evidence.snapshot.invalid',
                    'snapshot cannot be serialized as canonical JSON',
                ),
            ),
        )
    if raw != canonical:
        return SnapshotCheck(
            'invalid',
            (
                _diagnostic(
                    'evidence.snapshot.invalid',
                    'snapshot bytes are not in canonical compact form',
                ),
            ),
        )
    return None


def check_snapshot(
    root: Path, request_data: dict[str, Any], result: dict[str, Any]
) -> SnapshotCheck:
    """Classify existing evidence without writing or invoking old executors."""
    read = _read_snapshot(root)
    if read is None:
        return SnapshotCheck(
            'missing',
            (
                _diagnostic(
                    'evidence.snapshot.missing',
                    f'{SNAPSHOT_RELATIVE_PATH} is missing',
                ),
            ),
        )
    candidate, raw = read
    if isinstance(candidate, _InvalidDocument) or not isinstance(
        candidate, dict
    ):
        message = (
            candidate.message
            if isinstance(candidate, _InvalidDocument)
            else 'snapshot must be a JSON object'
        )
        return SnapshotCheck(
            'invalid',
            (_diagnostic('evidence.snapshot.invalid', message),),
        )
    canonical_issue = _canonical_issue(candidate, raw)
    if canonical_issue is not None:
        return canonical_issue

    snapshot_version = candidate.get('snapshotVersion')
    snapshot_entry = _entry(
        SNAPSHOT_COMPATIBILITY_REGISTRY,
        snapshot_version,
    )
    if snapshot_entry is None or snapshot_entry.status not in (
        'current',
        'compatible',
    ):
        return SnapshotCheck(
            'invalid',
            (_version_diagnostic('snapshotVersion', snapshot_version),),
        )
    if not isinstance(snapshot_version, str):
        return SnapshotCheck(
            'invalid',
            (_version_diagnostic('snapshotVersion', snapshot_version),),
        )
    parser = snapshot_entry.parser or SNAPSHOT_DATA_PARSERS.get(
        snapshot_version,
        validate_snapshot_document,
    )
    try:
        parsed = parser(candidate)
        if parsed is not None and not isinstance(parsed, dict):
            raise ValueError('snapshot parser did not return an object')
    except (TypeError, ValueError, KeyError) as exc:
        return SnapshotCheck(
            'invalid',
            (
                _diagnostic(
                    'evidence.snapshot.invalid',
                    f'invalid snapshot data: {exc}',
                ),
            ),
        )

    for field, registry in (
        (
            'protocolVersion',
            PROTOCOL_COMPATIBILITY_REGISTRY,
        ),
        (
            'profile',
            PROFILE_COMPATIBILITY_REGISTRY,
        ),
    ):
        entry = _entry(registry, candidate.get(field))
        if entry is None or entry.status not in ('current', 'compatible'):
            return SnapshotCheck(
                'invalid',
                (_version_diagnostic(field, candidate.get(field)),),
            )
        if entry.status != 'current':
            return SnapshotCheck(
                'stale',
                (
                    _diagnostic(
                        'evidence.snapshot.stale',
                        f'{field} recorded compatible non-current version '
                        f'{candidate.get(field)!r}',
                    ),
                ),
            )
    if snapshot_entry.status != 'current':
        return SnapshotCheck(
            'stale',
            (
                _diagnostic(
                    'evidence.snapshot.stale',
                    'snapshotVersion recorded compatible non-current version '
                    f'{candidate.get("snapshotVersion")!r}',
                ),
            ),
        )

    recorded_executor = candidate.get('executorVersion')
    if not isinstance(recorded_executor, str) or not recorded_executor:
        return SnapshotCheck(
            'invalid',
            (_version_diagnostic('executorVersion', recorded_executor),),
        )
    installed_executor = result.get('executorVersion')
    if recorded_executor != installed_executor:
        return SnapshotCheck(
            'stale',
            (
                _diagnostic(
                    'evidence.snapshot.stale',
                    f'executorVersion differs: expected {installed_executor!r}, '
                    f'observed {recorded_executor!r}',
                ),
            ),
        )

    expected = snapshot_from_result(request_data, result)
    field, expected_value, observed_value = _first_difference(
        expected, candidate
    )
    if field != 'snapshot':
        return SnapshotCheck(
            'stale',
            (
                _diagnostic(
                    'evidence.snapshot.stale',
                    f'{field} differs: expected {expected_value!r}, '
                    f'observed {observed_value!r}',
                ),
            ),
        )
    return SnapshotCheck('current', ())
