"""Verify publication campaign evidence across every declared shard."""

from __future__ import annotations

import argparse
import errno
import json
import sys
from pathlib import Path
from typing import Any

NATIVE_REQUIRED_CASES = (
    'test_live_process_query_never_sends_a_signal',
    'test_restart_recovers_setup_crashes_without_residue',
    'test_commit_crash_recovers_one_complete_batch',
    'test_restart_recovers_a_crash_during_recovery',
    'test_contenders_cannot_steal_live_publication_or_recovery',
    'test_first_extraction_recovers_removed_transaction_directories',
    'test_native_public_extraction_preserves_sources_and_publishes_rows',
    'test_bounded_download_rejects_gzip_before_stream_or_decoding',
    'test_transient_http_status_uses_the_configured_retry_budget',
    'test_redirect_credentials_are_confined_to_the_initial_origin',
    'test_json_secret_fields_remain_valid_json',
    'test_http_status_error_redacts_url_user_info',
    'test_cvm_metadata_failure_logs_redact_url_credentials',
)
NATIVE_OPTIONAL_SKIP = (
    'test_initial_ownership_temporary_cannot_alias_caller_data[symlink]'
)


def storage_labels(event: dict[str, Any]) -> set[str]:
    """Derive required storage dimensions from the recorded operation."""
    point = event['index']
    labels = {
        f'error:{point}:{number}' for number in (errno.ENOSPC, errno.EIO)
    }
    if event['edge'] != 'before':
        return labels
    for number in (errno.ENOSPC, errno.EIO):
        labels.add(f'persistent:{point}:{number}')
        if event['operation'] in {'write_bytes', 'copy2'}:
            labels.update(
                f'partial:{point}:{number}:{part}' for part in (0, 0.5, 1)
            )
    return labels


def expected_cases(report: dict[str, Any]) -> set[str]:
    """Derive completeness from traces independently of execution counters."""
    initial = report['initial_events']
    if not initial or [item['index'] for item in initial] != list(
        range(len(initial))
    ):
        raise ValueError('initial operation trace is empty or discontinuous')
    selected = [
        item
        for item in initial
        if item['index'] % report['shards'] == report['shard']
    ]
    recovery = report['recovery_events']
    if set(recovery) != {str(item['index']) for item in selected}:
        raise ValueError('not every first crash received a recovery trace')
    phases: dict[str, int] = {}
    for item in initial:
        if item['edge'] == 'after' and item['phase'] is not None:
            phases.setdefault(item['phase'], item['index'])
    labels = set()
    for event in selected:
        point = event['index']
        labels.add(f'crash:{point}')
        labels.update(storage_labels(event))
        nested = recovery[str(point)]
        if [item['index'] for item in nested] != list(range(len(nested))):
            raise ValueError('recovery operation trace is discontinuous')
        labels.update(f'nested:{point}:{item["index"]}' for item in nested)
        if point in phases.values():
            for item in nested:
                labels.update(
                    f'recovery-storage:{point}:{label}'
                    for label in storage_labels(item)
                )
    return labels


def verify_campaign(report: dict[str, Any]) -> int:
    """Require exact coverage, successful outcomes, and consistent totals."""
    expected = expected_cases(report)
    if report['status'] != 'passed' or report['failures']:
        raise ValueError('campaign did not finish successfully')
    for field in ('manifest', 'cases'):
        values = report[field]
        if len(values) != len(expected) or set(values) != expected:
            raise ValueError(
                f'{field} omits, duplicates, or invents campaign cases'
            )
    if not expected or any(
        report[field] != len(expected)
        for field in ('expected', 'attempted', 'passed')
    ):
        raise ValueError('campaign execution counts do not match its traces')
    return len(expected)


def verify_shards(paths: list[Path], shards: int) -> int:
    """Require all four input/backup scenarios and every shard of each."""
    if shards <= 0:
        raise ValueError('campaign shard count must be positive')
    reports: dict[tuple[bool, bool, int], dict[str, Any]] = {}
    total = 0
    for path in paths:
        report = json.loads(path.read_text())
        scenario = report['scenario']
        key = (scenario['existing'], scenario['copy_backups'], report['shard'])
        if key in reports or report['shards'] != shards:
            raise ValueError('duplicated scenario shard or wrong shard count')
        reports[key] = report
        total += verify_campaign(report)
    expected = {
        (existing, copy, shard)
        for existing in (False, True)
        for copy in (False, True)
        for shard in range(shards)
    }
    if set(reports) != expected:
        raise ValueError('campaign reports do not cover every scenario shard')
    for existing in (False, True):
        for copy in (False, True):
            traces = [
                reports[(existing, copy, shard)]['initial_events']
                for shard in range(shards)
            ]
            if any(trace != traces[0] for trace in traces):
                raise ValueError(
                    'shards enumerated different baseline operations'
                )
    return total


def verify_native(paths: list[Path]) -> int:
    """Require six native environments and genuine critical executions."""
    environments = set()
    total = 0
    for path in paths:
        report = json.loads(path.read_text())
        key = (report['system'], '.'.join(report['python'].split('.')[:2]))
        if (
            key in environments
            or report['status'] != 'passed'
            or report['exit_code'] != 0
            or report['issues']
        ):
            raise ValueError('native results are duplicated or unsuccessful')
        collected, outcomes = report['collected'], report['outcomes']
        if not collected or set(collected) != set(outcomes):
            raise ValueError('native tests were missing or never executed')
        for nodeid in collected:
            outcome = outcomes[nodeid]
            optional = (
                report['system'] == 'Windows'
                and nodeid.rsplit('::', 1)[-1] == NATIVE_OPTIONAL_SKIP
            )
            if outcome != 'passed' and not (outcome == 'skipped' and optional):
                raise ValueError(f'native case did not pass: {nodeid}')
        _require_native_behaviors(collected, outcomes)
        environments.add(key)
        total += sum(value == 'passed' for value in outcomes.values())
    expected = {
        (system, version)
        for system in ('Windows', 'Darwin')
        for version in ('3.12', '3.13', '3.14')
    }
    if environments != expected:
        raise ValueError('native reports do not cover all six environments')
    return total


def _require_native_behaviors(
    collected: list[str], outcomes: dict[str, str]
) -> None:
    for name in NATIVE_REQUIRED_CASES:
        matches = [
            nodeid
            for nodeid in collected
            if nodeid.rsplit('::', 1)[-1].split('[', 1)[0] == name
        ]
        if not matches or any(
            outcomes[nodeid] != 'passed' for nodeid in matches
        ):
            raise ValueError(f'native behavior was not exercised: {name}')


def main() -> int:
    """Validate downloaded CI evidence without creating OpenSpec artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path)
    parser.add_argument('--shards', type=int, default=8)
    parser.add_argument('--native-reports', type=Path)
    args = parser.parse_args()
    try:
        total = verify_shards(
            sorted(args.reports.rglob('campaign-*.json')), args.shards
        )
        if args.native_reports is not None:
            verify_native(sorted(args.native_reports.rglob('results.json')))
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.stderr.write(f'FAIL [RELEASE_EVIDENCE]: {error}\n')
        return 1
    sys.stdout.write(
        f'PASS [RELEASE_EVIDENCE]: {total} complete campaign cases\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
