"""Command-line entry point for ``harness-validate``."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, NoReturn

from harness.consumer_types import (
    ContractError,
    Diagnostic,
    DistributionVersionError,
)
from harness.consumer_validation import (
    execute_consumer_validation,
    verify_path_confinement,
)
from harness.consumer_validation_evidence import (
    SnapshotWriteError,
    publish_snapshot,
)
from harness.consumer_validation_evidence_schema import CHECK_SCHEMA_VERSION
from harness.consumer_validation_snapshot import (
    SnapshotReadError,
    check_snapshot,
)
from harness.paths import GitRootError, strict_repo_root

WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class ExecutionMetadataError(ContractError):
    """The execution interval cannot satisfy the telemetry contract."""


class ArgumentParseError(ContractError):
    """Command-line arguments violate the receiver contract."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ArgumentParseError(message)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _monotonic() -> float:
    return time.perf_counter()


def _error_diagnostic(request: str, code: str, message: str) -> dict[str, str]:
    return Diagnostic(
        request,
        'consumer-validation.cli',
        code,
        message,
    ).to_dict()


def _argument_request(argv: Sequence[str] | None) -> str:
    values = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(values):
        if value == '--request' and index + 1 < len(values):
            return values[index + 1]
        if value.startswith('--request='):
            return value.partition('=')[2]
    return '<command-line>'


def _emit_structured_error(diagnostic: dict[str, str]) -> None:
    sys.stderr.write(
        json.dumps(
            diagnostic,
            sort_keys=True,
            ensure_ascii=True,
            indent=None,
            separators=(',', ':'),
        )
        + '\n'
    )


def _emit_result(result: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + '\n'
    )


def _emit_human_diagnostics(diagnostics: Sequence[dict[str, str]]) -> None:
    for diagnostic in diagnostics:
        sys.stderr.write(
            f'[{diagnostic["code"]}] {diagnostic["item"]} '
            f'({diagnostic["validatorId"]}): {diagnostic["message"]}\n'
        )


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return (
        value.strftime('%Y-%m-%dT%H:%M:%S.')
        + f'{value.microsecond // 1000:03d}Z'
    )


def _finite_sample(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ExecutionMetadataError(
            f'{label} is not a finite monotonic-clock sample'
        )
    try:
        sample = float(value)
    except (TypeError, ValueError) as exc:
        raise ExecutionMetadataError(
            f'{label} is not a finite monotonic-clock sample'
        ) from exc
    if not math.isfinite(sample):
        raise ExecutionMetadataError(
            f'{label} is not a finite monotonic-clock sample'
        )
    return sample


def _execution_metadata(
    started_at: datetime,
    finished_at: datetime,
    started_sample: object,
    finished_sample: object,
) -> dict[str, object]:
    started = _finite_sample(started_sample, 'started monotonic sample')
    finished = _finite_sample(finished_sample, 'finished monotonic sample')
    delta = finished - started
    if not math.isfinite(delta) or delta < 0:
        raise ExecutionMetadataError(
            'execution interval has a non-finite or negative duration'
        )
    duration = round(delta, 6)
    if not math.isfinite(duration) or duration < 0:
        raise ExecutionMetadataError(
            'execution interval rounded duration is invalid'
        )
    if duration == 0:
        duration = 0.0
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=UTC)
    started_utc = started_at.astimezone(UTC)
    finished_utc = finished_at.astimezone(UTC)
    if finished_utc < started_utc:
        finished_utc = started_utc
    return {
        'startedAt': _format_timestamp(started_utc),
        'finishedAt': _format_timestamp(finished_utc),
        'durationSeconds': duration,
    }


def _check_envelope(
    result: dict[str, Any], status: str, diagnostics: Sequence[dict[str, str]]
) -> dict[str, Any]:
    ordered = sorted(
        diagnostics,
        key=lambda item: tuple(
            item[field]
            for field in ('item', 'validatorId', 'code', 'message', 'severity')
        ),
    )
    return {
        'schemaVersion': CHECK_SCHEMA_VERSION,
        'mode': 'check-result',
        'validation': result,
        'snapshotCheck': {
            'diagnostics': ordered,
            'exitCode': 0 if status == 'current' else 1,
            'status': status,
        },
    }


def _contract_code(error: ContractError) -> str:
    if isinstance(error, DistributionVersionError):
        return 'execution.executor.version-unavailable'
    if isinstance(error, SnapshotWriteError):
        return 'evidence.snapshot.write-failed'
    if isinstance(error, SnapshotReadError):
        return 'evidence.snapshot.read-failed'
    if isinstance(error, ExecutionMetadataError):
        return 'execution.metadata.invalid-duration'
    return 'execution.contract.invalid'


def main(
    argv: list[str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    utc_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
) -> int:
    """Run validation in raw, explicit-write, or read-only-check mode."""
    if wall_clock is not None and utc_clock is not None:
        raise TypeError('wall_clock and utc_clock are mutually exclusive')
    parser = _ArgumentParser(
        description='Validate consumer-owned skills, agents, and workflows.'
    )
    parser.add_argument(
        '--request',
        required=True,
        metavar='PATH',
        help='Repository-relative path to the validation request JSON document.',
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--write-result', action='store_true')
    modes.add_argument('--check-result', action='store_true')
    try:
        args = parser.parse_args(argv)
    except ArgumentParseError as exc:
        _emit_structured_error(
            _error_diagnostic(
                _argument_request(argv),
                'execution.contract.invalid',
                str(exc),
            )
        )
        return 2

    wall = wall_clock or utc_clock or _utc_now
    monotonic = monotonic_clock or _monotonic
    try:
        root = strict_repo_root()
    except GitRootError as exc:
        _emit_structured_error(
            _error_diagnostic(
                args.request, 'execution.git-root.unavailable', str(exc)
            )
        )
        return 2

    try:
        request_file = verify_path_confinement(
            root, args.request, 'request path', must_exist=True
        )
        request_data = json.loads(request_file.read_text(encoding='utf-8'))
    except (
        ContractError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        OSError,
    ) as exc:
        _emit_structured_error(
            _error_diagnostic(
                args.request,
                'request.read-failed',
                f'cannot read request JSON: {exc}',
            )
        )
        return 2

    try:
        started_at = wall()
        started_sample = monotonic()
        result = execute_consumer_validation(root, request_data)
        finished_sample = monotonic()
        finished_at = wall()
        result['executionMetadata'] = _execution_metadata(
            started_at,
            finished_at,
            started_sample,
            finished_sample,
        )
    except ContractError as exc:
        _emit_structured_error(
            _error_diagnostic(args.request, _contract_code(exc), str(exc))
        )
        return 2

    if result['exitCode'] != 0:
        if args.check_result:
            envelope = _check_envelope(result, 'not-evaluated', ())
            _emit_result(envelope)
        else:
            _emit_result(result)
        _emit_human_diagnostics(result['diagnostics'])
        return int(result['exitCode'])

    if args.write_result:
        try:
            publish_snapshot(root, request_data, result)
        except ContractError as exc:
            _emit_structured_error(
                _error_diagnostic(args.request, _contract_code(exc), str(exc))
            )
            return 2
        _emit_result(result)
        return 0

    if args.check_result:
        try:
            checked = check_snapshot(root, request_data, result)
        except ContractError as exc:
            _emit_structured_error(
                _error_diagnostic(args.request, _contract_code(exc), str(exc))
            )
            return 2
        envelope = _check_envelope(result, checked.status, checked.diagnostics)
        _emit_result(envelope)
        if checked.status != 'current':
            _emit_human_diagnostics(checked.diagnostics)
        return int(envelope['snapshotCheck']['exitCode'])

    _emit_result(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
