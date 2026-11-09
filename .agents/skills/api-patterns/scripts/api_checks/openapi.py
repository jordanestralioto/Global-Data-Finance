"""Structured JSON checks and explicitly limited dependency-free YAML triage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .contracts import FileResult, file_result
from .operations import HTTP_METHODS, check_operation


def resolve_local(value: Any, spec: dict[str, Any]) -> Any:
    """Resolve only local JSON pointers; never fetch a referenced URL/file."""
    seen: set[str] = set()
    while isinstance(value, dict) and isinstance(value.get('$ref'), str):
        reference = value['$ref']
        if not reference.startswith('#/') or reference in seen:
            return value
        seen.add(reference)
        resolved: Any = spec
        for part in unquote(reference[2:]).split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            if not isinstance(resolved, dict) or key not in resolved:
                return value
            resolved = resolved[key]
        value = resolved
    return value


def record_unresolved_reference(
    value: dict[str, Any], result: FileResult
) -> None:
    reference = value.get('$ref')
    if not isinstance(reference, str):
        result['issues'].append('[X] Reference $ref must be a string')
    elif reference.startswith('#/'):
        result['issues'].append(
            f'[X] Broken or cyclic local JSON pointer: {reference}'
        )
    else:
        result['unverified'].append(
            'Unresolved external reference or unsupported fragment; dependent checks remain unverified.'
        )


def read_parameters(
    value: Any, spec: dict[str, Any], result: FileResult
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        result['issues'].append('[X] Parameters must be an array')
        return []
    parameters = []
    for item in value:
        resolved = resolve_local(item, spec)
        if not isinstance(resolved, dict):
            result['issues'].append(
                '[X] Parameter must be an object/reference'
            )
        elif '$ref' in resolved:
            parameters.append(resolved)
            record_unresolved_reference(resolved, result)
        elif not all(
            isinstance(resolved.get(key), str) for key in ('in', 'name')
        ):
            result['issues'].append(
                '[X] Parameter name and in must be strings'
            )
        else:
            parameters.append(resolved)
    return parameters


def merge_parameters(
    inherited: list[dict[str, Any]], declared: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = {}
    unresolved = []
    for entry in inherited + declared:
        if '$ref' in entry:
            unresolved.append(entry)
        else:
            merged[(entry['in'], entry['name'])] = entry
    return list(merged.values()) + unresolved


def check_openapi_spec(path: Path, content: str) -> FileResult:
    if path.suffix.lower() != '.json':
        return check_openapi_text(path, content)
    result = file_result(path, 'openapi', 'structured-json')
    try:
        spec = json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        result['issues'].append(f'[X] JSON parse error: {exc}')
        result['analysis'] = 'inspection-error'
        return result
    if not isinstance(spec, dict):
        result['issues'].append('[X] OpenAPI document must be a JSON object')
        return result
    if 'openapi' not in spec and 'swagger' not in spec:
        result['issues'].append('[X] No OpenAPI/Swagger version found')
    info = spec.get('info', {})
    for name in ('title', 'version'):
        if not isinstance(info, dict) or not info.get(name):
            result['issues'].append(f'[!] API {name} missing')
    paths = spec.get('paths', {})
    webhooks = spec.get('webhooks', {})
    if not isinstance(paths, dict):
        result['issues'].append('[X] Paths must be an object')
        return result
    if not paths and not webhooks:
        result['issues'].append('[X] No paths or webhooks defined')
    check_path_items(paths, spec, result)
    if isinstance(webhooks, dict):
        check_path_items(webhooks, spec, result, webhook=True)
    else:
        result['issues'].append('[X] Webhooks must be an object')
    result['unverified'].append(
        'Use the project OpenAPI validator for schema validity; this tool does not prove runtime behavior or resolve external references.'
    )
    return result


def check_path_items(
    paths: dict[str, Any],
    spec: dict[str, Any],
    result: FileResult,
    *,
    webhook: bool = False,
) -> None:
    for path, raw_item in paths.items():
        item = resolve_local(raw_item, spec)
        if not isinstance(item, dict):
            result['issues'].append(f'[X] {path}: Path item must be an object')
            continue
        if '$ref' in item:
            record_unresolved_reference(item, result)
            continue
        path_parameters = read_parameters(item.get('parameters'), spec, result)
        for method, details in item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(details, dict):
                result['issues'].append(
                    f'[X] {method.upper()} {path}: Operation must be an object'
                )
                continue
            parameters = merge_parameters(
                path_parameters,
                read_parameters(details.get('parameters'), spec, result),
            )
            label = f'webhook/{path}' if webhook else path
            check_operation(method, label, details, spec, parameters, result)


def check_openapi_text(path: Path, content: str) -> FileResult:
    result = file_result(path, 'openapi', 'yaml-text-only')
    for name, pattern in (
        ('OpenAPI/Swagger version', r'^\s*(openapi|swagger)\s*:'),
        ('paths or webhooks', r'^\s*(paths|webhooks)\s*:'),
    ):
        if re.search(pattern, content, re.M):
            result['passed'].append(f'[OK] Text contains {name} marker')
        else:
            result['issues'].append(f'[!] No {name} text marker found')
    result['issues'].append(
        '[!] YAML text-only triage: syntax and per-operation contracts were not parsed; use the project validator or export JSON'
    )
    result['unverified'].append(
        'YAML syntax, references, security requirements, parameters and operation behavior.'
    )
    return result
