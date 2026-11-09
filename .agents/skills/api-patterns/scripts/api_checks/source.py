"""Language-neutral lexical leads, never a route-level security verdict."""

from __future__ import annotations

from pathlib import Path

from .contracts import FileResult, file_result, has_pattern

MARKERS = {
    'input schema': (r'\b(schema|pydantic|zod|validate|validates)\b',),
    'authentication': (r'\b(auth|jwt|bearer|session|current_user)\b',),
    'rate limit': (r'rate.?limit|throttle|Retry-After',),
    'precondition': (r'ETag|If-Match|If-None-Match|optimistic',),
    'idempotency': (r'Idempotency-Key|idempotenc|deduplic',),
    'streaming': (r'text/event-stream|EventSource|StreamingResponse',),
    'lifecycle': (r'\b(Deprecation|Sunset|deprecated)\b',),
}
MANUAL_CHECKS = [
    'Bind each protected resource to the caller or tenant in the actual policy/query.',
    'Trace input validation and sanitized errors through the project middleware.',
    'Verify quota and cost reservation before external or expensive work.',
    'Verify persistent idempotency and atomic concurrency enforcement per operation.',
    'Measure request duration before choosing sync, job, callback or stream.',
]


def check_api_code(path: Path, content: str) -> FileResult:
    result = file_result(path, 'code', 'lexical-markers')
    result['passed'].append('[OK] UTF-8 source read; no language parser used')
    result['unverified'].extend(MANUAL_CHECKS)
    for label, patterns in MARKERS.items():
        if has_pattern(content, patterns):
            result['unverified'].append(
                f'{label.capitalize()} markers observed; verify their scope and enforcement.'
            )
    check_identity_leads(content, result)
    check_cors_leads(content, result)
    check_webhook_leads(content, result)
    if has_pattern(
        content,
        (
            r'detail\s*=\s*str\(',
            r'(?:res|response)\.(?:json|send)\(\s*(?:err|error|exception)\b',
        ),
    ):
        result['issues'].append(
            '[!] Exception-to-response marker; check the actual sanitizer and error boundary'
        )
    return result


def check_identity_leads(content: str, result: FileResult) -> None:
    if has_pattern(
        content,
        (
            r'(?:ownerId|userId|tenantId)\s*:\s*(?:input|req\.body)\.(?:userId|tenantId)',
            r'(?:owner_id|tenant_id)\s*[:=]\s*(?:body|payload|input)\[',
        ),
    ):
        result['issues'].append(
            '[!] Client identity flows into an ownership marker; verify authorization against trusted context'
        )


def check_cors_leads(content: str, result: FileResult) -> None:
    wildcard = has_pattern(
        content,
        (
            r"""["']?Access-Control-Allow-Origin["']?\s*[:=]\s*["']\*["']""",
            r"""allow_origins\s*=\s*\[\s*["']\*["']""",
        ),
    )
    if not wildcard:
        return
    result['issues'].append(
        '[!] Wildcard CORS marker; check intended origins, credentials and proxy topology'
    )
    if has_pattern(
        content,
        (
            r"""["']?Access-Control-Allow-Credentials["']?\s*[:=]\s*(?:true|["']true["'])""",
            r'allow_credentials\s*=\s*True',
            r'credentials\s*:\s*true',
        ),
    ):
        result['issues'].append(
            '[!] Wildcard and credential markers coexist in this file; verify whether they configure the same response'
        )


def check_webhook_leads(content: str, result: FileResult) -> None:
    if not has_pattern(
        content,
        (
            r"""["'][^"'\n]*/webhooks?(?:/|["'])""",
            r'\b(?:handle|receive|process)_?webhook\b',
        ),
    ):
        return
    for label, patterns in (
        (
            'signature verification',
            (
                r'verify\w*signature|signature\w*verify|hmac|compare_digest|timingSafeEqual|constructEvent',
            ),
        ),
        ('replay window', (r'timestamp|replay|tolerance',)),
        ('persistent deduplication', (r'event[_-]?id|deduplic|idempotenc',)),
    ):
        if not has_pattern(content, patterns):
            result['issues'].append(
                f'[!] Webhook endpoint marker without {label} markers; trace middleware and storage'
            )
    result['unverified'].append(
        'Webhook lexical markers cannot prove signature, replay or deduplication enforcement for a particular handler.'
    )
