"""Isolated consumer validation protocol and validator engine."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
from typing import Any

from harness.consumer_discovery import (
    apply_scope_selection,
    discover_scope_items,
)
from harness.consumer_types import (
    SCOPE_VALIDATORS,
    BoundaryError,
    ContractError,
    Diagnostic,
    DistributionVersionError,
)
from harness.paths import GitRootError, strict_repo_root

PROTOCOL_VERSION = 'consumer-validation-v1'
PROFILE = 'consumer-isolated-v1'
SUPPORTED_SCOPES = ('skills', 'agents', 'workflows')


def get_executor_version() -> str:
    """Return the installed central-skills distribution version."""
    try:
        return importlib.metadata.version('central-skills')
    except (importlib.metadata.PackageNotFoundError, Exception) as exc:
        raise DistributionVersionError(
            'cannot read installed distribution version for central-skills'
        ) from exc


def _validate_rel_path_string(path_str: str, context: str) -> None:
    if not path_str or not isinstance(path_str, str):
        raise ContractError(f'{context} must be a non-empty string')
    if path_str.startswith('/') or '\\' in path_str or ':' in path_str:
        raise ContractError(f'{context} must be a relative POSIX path')
    posix = PurePosixPath(path_str)
    if posix.is_absolute() or any(
        part in ('.', '..', '') for part in posix.parts
    ):
        raise ContractError(
            f'{context} must not contain traversal or empty segments'
        )


def verify_path_confinement(
    root: Path, rel_path: str, context: str, must_exist: bool = False
) -> Path:
    """Ensure path is within root and does not escape via traversal or symlinks."""
    _validate_rel_path_string(rel_path, context)
    target = root / rel_path
    if must_exist and not target.exists():
        raise ContractError(f'{context} does not exist: {rel_path}')
    try:
        resolved_root = root.resolve()
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(resolved_root):
            raise BoundaryError(
                f'{context} escapes repository root: {rel_path}'
            )
    except OSError as exc:
        raise BoundaryError(
            f'{context} cannot be resolved safely: {rel_path}'
        ) from exc
    return target


def _validate_scope_filters(
    scope_name: str, scope_def: dict[str, Any]
) -> None:
    is_required = bool(scope_def.get('required'))
    for filter_key in ('include', 'exclude'):
        if filter_key not in scope_def:
            continue
        val = scope_def[filter_key]
        if is_required and val:
            raise ContractError(
                f"required scope '{scope_name}' cannot use include or exclude filters"
            )
        if not isinstance(val, list) or any(
            not isinstance(x, str) for x in val
        ):
            raise ContractError(
                f"scope '{scope_name}.{filter_key}' must be an array of strings"
            )
        for item_name in val:
            _validate_rel_path_string(
                item_name, f"scope '{scope_name}.{filter_key}' item"
            )


def _validate_scope_definition(scope_name: str, scope_def: Any) -> bool:
    if not isinstance(scope_def, dict):
        raise ContractError(f"scope '{scope_name}' must be an object")
    extra_keys = set(scope_def) - {'path', 'required', 'include', 'exclude'}
    if extra_keys:
        raise ContractError(
            f"unsupported fields in scope '{scope_name}': {sorted(extra_keys)}"
        )
    if 'path' not in scope_def or 'required' not in scope_def:
        raise ContractError(
            f"scope '{scope_name}' must contain 'path' and 'required'"
        )
    if not isinstance(scope_def['required'], bool):
        raise ContractError(f"scope '{scope_name}.required' must be a boolean")
    _validate_rel_path_string(scope_def['path'], f"scope '{scope_name}.path'")
    _validate_scope_filters(scope_name, scope_def)
    return bool(scope_def['required'])


def parse_and_validate_request(
    data: Any,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    """Validate request document according to closed schema and contract."""
    if not isinstance(data, dict):
        raise ContractError('request document must be a JSON object')
    extra_top = set(data) - {'protocolVersion', 'profile', 'scopes'}
    if extra_top:
        raise ContractError(f'unsupported request fields: {sorted(extra_top)}')
    if data.get('protocolVersion') != PROTOCOL_VERSION:
        raise ContractError(
            f"unsupported protocolVersion '{data.get('protocolVersion')}' (expected '{PROTOCOL_VERSION}')"
        )
    if data.get('profile') != PROFILE:
        raise ContractError(
            f"unsupported profile '{data.get('profile')}' (expected '{PROFILE}')"
        )
    scopes = data.get('scopes')
    if not isinstance(scopes, dict) or not scopes:
        raise ContractError("'scopes' must be a non-empty object")
    extra_scopes = set(scopes) - set(SUPPORTED_SCOPES)
    if extra_scopes:
        raise ContractError(
            f'unsupported scopes for {PROFILE}: {sorted(extra_scopes)}'
        )
    has_required = any(
        _validate_scope_definition(s_name, s_def)
        for s_name, s_def in scopes.items()
    )
    if not has_required:
        raise ContractError(
            'at least one requested scope must specify required: true'
        )
    return PROTOCOL_VERSION, PROFILE, scopes


def compute_stable_identity(
    executor_version: str,
    protocol_version: str,
    profile: str,
    raw_scopes: dict[str, dict[str, Any]],
    effective_scopes: list[dict[str, Any]],
    validator_ids: list[str],
) -> str:
    normalized_scopes = [
        {
            'exclude': sorted(raw_scopes[s_name].get('exclude', [])),
            'include': sorted(raw_scopes[s_name].get('include', [])),
            'name': s_name,
            'path': raw_scopes[s_name]['path'],
            'required': raw_scopes[s_name]['required'],
        }
        for s_name in sorted(raw_scopes)
    ]
    canonical_payload = {
        'effectiveScopes': effective_scopes,
        'executorVersion': executor_version,
        'normalizedRequest': {
            'profile': profile,
            'protocolVersion': protocol_version,
            'scopes': normalized_scopes,
        },
        'validatorIds': sorted(validator_ids),
    }
    raw_bytes = json.dumps(
        canonical_payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(raw_bytes).hexdigest()


def execute_consumer_validation(
    root: Path | None, request_data: dict[str, Any]
) -> dict[str, Any]:
    if root is None:
        try:
            root = strict_repo_root()
        except GitRootError as exc:
            raise ContractError(str(exc)) from exc
    executor_version = get_executor_version()
    proto, prof, scopes = parse_and_validate_request(request_data)
    for s_name, s_def in scopes.items():
        verify_path_confinement(
            root,
            s_def['path'],
            f"scope '{s_name}.path'",
            must_exist=False,
        )
    all_diagnostics: list[Diagnostic] = []
    effective_scopes_list: list[dict[str, Any]] = []
    active_validators: set[str] = set()
    total_effective_items = 0
    passed_items_count = 0
    failed_items_count = 0
    skipped_scopes_count = 0

    for scope_name in sorted(scopes):
        scope_def = scopes[scope_name]
        scope_path_str = scope_def['path']
        is_required = scope_def['required']
        scope_dir = root / scope_path_str
        if not scope_dir.exists():
            if not is_required:
                skipped_scopes_count += 1
                effective_scopes_list.append(
                    {
                        'excludedItems': [],
                        'items': [],
                        'name': scope_name,
                        'path': scope_path_str,
                        'required': False,
                        'status': 'skipped',
                    }
                )
            else:
                diag = Diagnostic(
                    scope_path_str,
                    'scope.missing',
                    'scope.missing',
                    f"required scope '{scope_name}' path does not exist: {scope_path_str}",
                )
                all_diagnostics.append(diag)
                effective_scopes_list.append(
                    {
                        'excludedItems': [],
                        'items': [],
                        'name': scope_name,
                        'path': scope_path_str,
                        'required': True,
                        'status': 'failed',
                    }
                )
                for v_id in SCOPE_VALIDATORS[scope_name]:
                    active_validators.add(v_id)
            continue
        discovered = discover_scope_items(root, scope_name, scope_path_str)
        if not discovered:
            if is_required:
                diag = Diagnostic(
                    scope_path_str,
                    'scope.empty',
                    'scope.empty',
                    f"required scope '{scope_name}' has no discovered items",
                )
                all_diagnostics.append(diag)
                effective_scopes_list.append(
                    {
                        'excludedItems': [],
                        'items': [],
                        'name': scope_name,
                        'path': scope_path_str,
                        'required': True,
                        'status': 'failed',
                    }
                )
                for v_id in SCOPE_VALIDATORS[scope_name]:
                    active_validators.add(v_id)
            else:
                skipped_scopes_count += 1
                effective_scopes_list.append(
                    {
                        'excludedItems': [],
                        'items': [],
                        'name': scope_name,
                        'path': scope_path_str,
                        'required': False,
                        'status': 'skipped',
                    }
                )
            continue
        try:
            effective, excluded = apply_scope_selection(
                scope_name, scope_def, discovered
            )
        except ValueError as exc:
            raise ContractError(str(exc)) from exc
        total_effective_items += len(effective)
        scope_item_diags: list[Diagnostic] = []
        for item in effective:
            for v_id in SCOPE_VALIDATORS[scope_name]:
                active_validators.add(v_id)
            item_diags = item.validate(root, scope_name)
            scope_item_diags.extend(item_diags)
            if item_diags:
                failed_items_count += 1
            else:
                passed_items_count += 1
        all_diagnostics.extend(scope_item_diags)
        scope_status = 'failed' if scope_item_diags else 'passed'
        effective_scopes_list.append(
            {
                'excludedItems': [
                    it.to_dict()
                    for it in sorted(excluded, key=lambda x: x.name)
                ],
                'items': [
                    it.to_dict()
                    for it in sorted(effective, key=lambda x: x.name)
                ],
                'name': scope_name,
                'path': scope_path_str,
                'required': is_required,
                'status': scope_status,
            }
        )
    sorted_diags = sorted(
        all_diagnostics,
        key=lambda d: (d.item, d.validator_id, d.code, d.message),
    )
    is_failed = bool(sorted_diags)
    status_str = 'failed' if is_failed else 'passed'
    exit_code = 1 if is_failed else 0
    validator_results = [
        {
            'id': v_id,
            'status': (
                'failed'
                if any(d.validator_id == v_id for d in sorted_diags)
                else 'passed'
            ),
        }
        for v_id in sorted(active_validators)
    ]
    stable_id = compute_stable_identity(
        executor_version,
        proto,
        prof,
        scopes,
        effective_scopes_list,
        list(active_validators),
    )
    counts = {
        'errors': len(sorted_diags),
        'failed': failed_items_count,
        'items': total_effective_items,
        'passed': passed_items_count,
        'scopes': len(scopes),
        'skipped': skipped_scopes_count,
    }
    return {
        'counts': counts,
        'diagnostics': [d.to_dict() for d in sorted_diags],
        'effectiveScopes': effective_scopes_list,
        'executorVersion': executor_version,
        'exitCode': exit_code,
        'profile': prof,
        'protocolVersion': proto,
        'stableContentIdentity': stable_id,
        'status': status_str,
        'validators': validator_results,
    }
