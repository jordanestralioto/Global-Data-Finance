"""Review declared OpenAPI operation contracts without inferring runtime safety."""

from __future__ import annotations

import re
from typing import Any

from .contracts import FileResult

HTTP_METHODS = frozenset(
    {
        'get',
        'post',
        'put',
        'patch',
        'delete',
        'options',
        'head',
        'trace',
    }
)
MUTATING_METHODS = frozenset({'post', 'put', 'patch', 'delete'})


def parameter_names(
    parameters: list[dict[str, Any]], location: str
) -> set[str]:
    return {
        str(parameter['name']).lower()
        for parameter in parameters
        if parameter.get('in') == location and 'name' in parameter
    }


def check_operation(
    method: str,
    path: str,
    details: dict[str, Any],
    spec: dict[str, Any],
    parameters: list[dict[str, Any]],
    result: FileResult,
) -> None:
    label = f'{method.upper()} {path}'
    responses = details.get('responses', {})
    if not isinstance(responses, dict) or not responses:
        result['issues'].append(f'[X] {label}: No responses defined')
        responses = {}
    codes = {str(code) for code in responses}
    if not details.get('summary') and not details.get('description'):
        result['issues'].append(f'[!] {label}: No summary/description')
    check_security(label, details, spec, result)
    if not any(code.startswith(('4', 'default')) for code in codes):
        result['issues'].append(
            f'[!] {label}: No explicit client/default error response'
        )
    for name in re.findall(r'{([^}/]+)}', path):
        declarations = [
            item
            for item in parameters
            if item.get('in') == 'path' and item.get('name') == name
        ]
        if not declarations and any('$ref' in item for item in parameters):
            result['unverified'].append(
                f'{label}: Cannot verify path parameter {name} through unresolved references.'
            )
        elif not declarations:
            result['issues'].append(
                f'[X] {label}: Missing path parameter declaration for {{{name}}}'
            )
        elif any(item.get('required') is not True for item in declarations):
            result['issues'].append(
                f'[X] {label}: Path parameter {name} must be required'
            )
    if method in MUTATING_METHODS:
        check_mutation(method, label, details, spec, parameters, result)
    if '202' in codes:
        result['unverified'].append(
            f'{label}: Verify the 202 status resource/callback, retry behavior and durable job acceptance.'
        )
    if details.get('deprecated') is True:
        result['passed'].append(f'[OK] {label}: Deprecation is declared')
    if 'webhook' in path.lower():
        headers = parameter_names(parameters, 'header')
        if not headers.intersection(
            {
                'x-signature',
                'x-webhook-signature',
                'authorization',
                'stripe-signature',
                'x-hub-signature-256',
            }
        ):
            result['issues'].append(
                f'[!] {label}: No recognized signature/auth header; review the provider contract'
            )
        result['unverified'].append(
            f'{label}: Verify raw-body signature, timestamp/replay policy and persistent event deduplication.'
        )


def check_security(
    label: str,
    details: dict[str, Any],
    spec: dict[str, Any],
    result: FileResult,
) -> None:
    requirements = details.get('security', spec.get('security'))
    if requirements is None:
        result['issues'].append(
            f'[!] {label}: No security requirement declared; defining a scheme alone does not apply it'
        )
    elif requirements == []:
        result['unverified'].append(
            f'{label}: Explicitly public operation; confirm that anonymous access is intended.'
        )
    elif isinstance(requirements, list) and any(
        item == {} for item in requirements
    ):
        result['unverified'].append(
            f'{label}: Security alternatives permit anonymous access.'
        )
    else:
        result['unverified'].append(
            f'{label}: Security is declared; verify runtime authentication and resource authorization.'
        )


def check_mutation(
    method: str,
    label: str,
    details: dict[str, Any],
    spec: dict[str, Any],
    parameters: list[dict[str, Any]],
    result: FileResult,
) -> None:
    headers = parameter_names(parameters, 'header')
    hints = f'{label} {details.get("summary", "")} {details.get("description", "")}'
    if (
        method == 'post'
        and re.search(
            r'\b(?:payments?|charges?|transfers?|exports?|jobs?|keys?)\b',
            hints,
            re.I,
        )
        and 'idempotency-key' not in headers
        and not any('$ref' in item for item in parameters)
    ):
        result['issues'].append(
            f'[!] {label}: Critical-looking POST without Idempotency-Key; verify an equivalent persistent deduplication contract, including with 202'
        )
    if method in {'put', 'patch', 'delete'}:
        result['unverified'].append(
            f'{label}: Verify atomic If-Match/version enforcement; an ETag response alone does not prevent lost updates.'
        )
    if (
        method in {'post', 'put', 'patch'}
        and 'swagger' not in spec
        and 'requestBody' not in details
    ):
        result['issues'].append(
            f'[!] {label}: No requestBody declared; confirm this operation needs no input body'
        )
