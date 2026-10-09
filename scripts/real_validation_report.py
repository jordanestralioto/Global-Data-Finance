"""Deterministic, secret-safe persistence for real-validation evidence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from .real_validation_types import CaseStatus, ValidationCase

REPORT_SCHEMA_VERSION = 2
_STATUS_ORDER: tuple[CaseStatus, ...] = (
    'passed',
    'failed',
    'skipped',
    'external_failure',
    'not_published',
)
_SECRET_PATTERN = re.compile(
    r'(?i)(\b(?:authorization|bearer|cookie|password|passwd|secret|token|'
    r'api[_-]?key)\b\s*[:=]\s*)[^\s,;]+'
)
_SECRET_KEY_PATTERN = re.compile(
    r'(?i)^(?:authorization|bearer|cookie|password|passwd|secret|token|'
    r'api[_-]?key)$'
)


class ReportFormatError(ValueError):
    """Indicate malformed manifest or result evidence."""


def redact(value: Any) -> Any:
    """Redact common credential-shaped values recursively."""
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r'\1[REDACTED]', value)
    if isinstance(value, Mapping):
        return {
            str(key): (
                '[REDACTED]'
                if isinstance(key, str) and _SECRET_KEY_PATTERN.fullmatch(key)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (bytes, bytearray)
    ):
        return [redact(item) for item in value]
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write one JSON document with stable serialization."""
    encoded = (
        json.dumps(
            redact(payload),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + '\n'
    )
    atomic_write(path, encoded)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object and reject non-object evidence."""
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReportFormatError(
            f'cannot read JSON report {path}: {error}'
        ) from error
    if not isinstance(payload, dict):
        raise ReportFormatError(f'JSON report must contain an object: {path}')
    return payload


def write_results(
    path: Path, results: Mapping[str, Mapping[str, Any]]
) -> None:
    """Rewrite one sorted JSONL result per case, replacing prior retries."""
    lines = [
        json.dumps(
            redact(results[case_id]),
            ensure_ascii=True,
            sort_keys=True,
            separators=(',', ':'),
        )
        for case_id in sorted(results)
    ]
    atomic_write(path, '\n'.join(lines) + ('\n' if lines else ''))


def read_results(path: Path) -> dict[str, dict[str, Any]]:
    """Read JSONL evidence and enforce one current result per case."""
    if not path.exists():
        return {}
    results: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReportFormatError(
            f'cannot read results report {path}: {error}'
        ) from error
    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReportFormatError(
                f'invalid result JSON at {path}:{line_number}: {error}'
            ) from error
        if not isinstance(value, dict) or not isinstance(
            value.get('caseId'), str
        ):
            raise ReportFormatError(
                f'result at {path}:{line_number} lacks a string caseId'
            )
        case_id = value['caseId']
        if case_id in results:
            raise ReportFormatError(
                f'duplicate result for case {case_id!r} in {path}'
            )
        results[case_id] = value
    return results


def build_case_result(
    case: ValidationCase,
    status: CaseStatus = 'failed',
    message: str = 'case did not produce a result',
) -> dict[str, Any]:
    """Build a complete report record with fresh mutable containers."""
    return {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'caseId': case.case_id,
        'source': case.source,
        'document': case.document,
        'year': case.year,
        'inputPath': case.input_path,
        'inputSizeBytes': case.input_size_bytes,
        'inputSha256': case.input_sha256,
        'command': case.command(),
        'published': None,
        'publicResult': None,
        'artifactCount': 0,
        'artifacts': [],
        'recordCount': 0,
        'schema': {},
        'temporaryFiles': [],
        'temporaryFilesAfterCleanup': [],
        'status': status,
        'message': message,
        'durationSeconds': 0.0,
    }


def build_summary(
    expected_case_ids: Sequence[str],
    results: Mapping[str, Mapping[str, Any]],
    duration_seconds: float,
) -> dict[str, Any]:
    """Build the aggregate status table required by the campaign contract."""
    counts = dict.fromkeys(_STATUS_ORDER, 0)
    expected = set(expected_case_ids)
    for result in results.values():
        if result.get('caseId') not in expected:
            continue
        status = result.get('status')
        if status in counts:
            counts[status] += 1
    executed = expected & set(results)
    return {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'durationSeconds': round(max(duration_seconds, 0.0), 6),
        'totalCombinations': len(expected),
        'totalExecuted': len(executed),
        'totalNotExecuted': len(expected - executed),
        'totalPublished': sum(
            result.get('published') is True
            for result in results.values()
            if result.get('caseId') in expected
        ),
        'totalApproved': counts['passed'],
        'totalNotPublished': counts['not_published'],
        'totalFunctionalFailures': counts['failed'],
        'totalExternalFailures': counts['external_failure'],
        'totalSkipped': counts['skipped'],
        'statusCounts': counts,
        'unclassifiedCaseIds': sorted(expected - executed),
    }


def validate_status(value: object) -> CaseStatus:
    """Return a valid status or reject malformed evidence."""
    if value not in _STATUS_ORDER:
        raise ReportFormatError(f'invalid campaign status: {value!r}')
    return value


def atomic_write(path: Path, content: str) -> None:
    """Publish report content through a temporary file and atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f'.{path.name}.', dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor, 'w', encoding='utf-8', newline=''
        ) as handle:
            handle.write(content)
        temporary_path.replace(path)
    except (OSError, UnicodeError):
        with suppress(OSError):
            temporary_path.unlink()
        raise
