"""Enumerate complete publication and nested recovery fault campaigns."""

from __future__ import annotations

import argparse
import errno
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tests.support.parquet_verifier import ParquetVerifier
from tests.support.publication_campaign_worker import run_child
from tests.support.publication_crashes import ARTIFACT_NAMES, CRASH_EXIT


def prepare_destination(
    root: Path, payload_root: Path, *, existing: bool
) -> dict[str, bytes]:
    """Create independent caller bytes and optionally old Parquet outputs."""
    root.mkdir()
    original = {
        'caller.txt': b'caller-owned bytes',
        'source.zip': b'caller ZIP',
    }
    original['caller-data/keep.txt'] = b'caller-owned child'
    if existing:
        original.update(
            {
                name: (payload_root / f'old-{name}').read_bytes()
                for name in ARTIFACT_NAMES
            }
        )
    for name, data in original.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    return original


def assert_recovered(
    root: Path,
    original: dict[str, bytes],
    payload_root: Path,
    *,
    decision: str,
) -> str:
    """Compare the entire destination with complete old and new snapshots."""
    actual = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob('*')
        if path.is_file()
    }
    new = original | {
        name: (payload_root / f'new-{name}').read_bytes()
        for name in ARTIFACT_NAMES
    }
    if actual not in (original, new):
        changed = sorted(
            name
            for name in actual.keys() | original.keys()
            if actual.get(name) != original.get(name)
        )
        raise AssertionError(
            f'mixed batch or caller/residue changes: {changed}'
        )
    directories = {
        path.relative_to(root).as_posix()
        for path in root.rglob('*')
        if path.is_dir()
    }
    if directories != {'caller-data'}:
        raise AssertionError(
            f'orphan directories after recovery: {directories}'
        )
    batch = 'old' if actual == original else 'new'
    if decision != batch:
        raise AssertionError(f'journal requires {decision}, recovered {batch}')
    return batch


def journal_decision(root: Path, *, fallback: str) -> str:
    """Read the independent persisted commit decision before recovery."""
    journals = list(root.rglob('.publication-journal.json'))
    if not journals:
        return fallback
    if len(journals) != 1:
        raise AssertionError('multiple authoritative journals in one fixture')
    phase = json.loads(journals[0].read_text())['phase']
    return 'new' if phase in {'COMMITTED', 'CLEANUP_PENDING'} else 'old'


def traced_decision(events: list[dict[str, Any]]) -> str:
    """Distinguish an uncreated journal from a removed committed journal."""
    phases = [event['phase'] for event in events if event['phase'] is not None]
    return (
        'new'
        if phases and phases[-1] in {'COMMITTED', 'CLEANUP_PENDING'}
        else 'old'
    )


def _require_result(result: dict[str, Any], *, crash: bool = False) -> None:
    if crash:
        if result['exit_code'] != CRASH_EXIT or not result['fired']:
            raise AssertionError(f'crash point was not reached: {result}')
    elif result['exit_code'] != 0 or result['error'] is not None:
        raise AssertionError(f'uninterrupted recovery failed: {result}')


class Campaign:
    """Keep execution, expected cases, and independent recovery evidence."""

    def __init__(
        self,
        root: Path,
        payload_root: Path,
        report_path: Path,
        *,
        existing: bool,
        copy_backups: bool,
        shard: int,
        shards: int,
        verifier: ParquetVerifier,
    ) -> None:
        """Initialize one deterministic scenario shard."""
        self.root = root
        self.payload_root = payload_root
        self.report_path = report_path
        self.sequence = 0
        self.verifier = verifier
        self.report: dict[str, Any] = {
            'scenario': {'existing': existing, 'copy_backups': copy_backups},
            'shard': shard,
            'shards': shards,
            'expected': 0,
            'attempted': 0,
            'passed': 0,
            'failures': [],
            'initial_events': [],
            'recovery_events': {},
            'manifest': [],
            'cases': [],
            'status': 'running',
        }
        root.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """Persist incomplete evidence as well as completed results."""
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(self.report, indent=2) + '\n')

    def prepare(self) -> tuple[Path, dict[str, bytes]]:
        """Create a fresh filesystem for every injected fault."""
        destination = self.root / f'case-{self.sequence}'
        self.sequence += 1
        return destination, prepare_destination(
            destination,
            self.payload_root,
            existing=self.report['scenario']['existing'],
        )

    def child(self, destination: Path, **kwargs: Any) -> dict[str, Any]:
        """Run the common worker with this scenario's backup policy."""
        return run_child(
            destination,
            self.payload_root,
            copy_backups=self.report['scenario']['copy_backups'],
            **kwargs,
        )

    def recover(
        self, destination: Path, original: dict[str, bytes], decision: str
    ) -> None:
        """Require repeated recovery and the independent journal oracle."""
        decision = journal_decision(destination, fallback=decision)
        _require_result(self.child(destination, action='repeat'))
        assert_recovered(
            destination,
            original,
            self.payload_root,
            decision=decision,
        )
        self.verifier.verify(destination)

    def execute(
        self,
        label: str,
        fault: dict[str, Any],
        first: int | None = None,
    ) -> None:
        """Inject one recorded fault and retain any failed filesystem."""
        self.report['attempted'] += 1
        destination, original = self.prepare()
        try:
            decision = 'old'
            if first is not None:
                initial = self.child(
                    destination,
                    fault={'index': first, 'kind': 'exit'},
                )
                _require_result(initial, crash=True)
                decision = journal_decision(
                    destination, fallback=traced_decision(initial['events'])
                )
            result = self.child(
                destination,
                action='recover' if first is not None else 'commit',
                fault=fault,
            )
            self.require_injection(result, fault)
            if first is None:
                decision = traced_decision(result['events'])
            self.recover(destination, original, decision)
            self.report['passed'] += 1
            self.report['cases'].append(label)
            shutil.rmtree(destination)
        except Exception as error:
            self.report['failures'].append(
                {
                    'case': label,
                    'error': str(error),
                    'path': str(destination),
                }
            )
            self.save()
            raise

    @staticmethod
    def require_injection(
        result: dict[str, Any], fault: dict[str, Any]
    ) -> None:
        """Reject missed faults and diagnostic causes lost by translation."""
        if fault['kind'] == 'exit':
            _require_result(result, crash=True)
        elif result['exit_code'] != 0 or not result['fired']:
            raise AssertionError(f'storage fault was not reached: {result}')
        elif result['error'] is not None and not any(
            item['errno'] == fault['errno'] for item in result['error']
        ):
            raise AssertionError(
                f'injected diagnostic cause lost: {result["error"]}'
            )

    def trace_recovery(self, point: int) -> list[dict[str, Any]]:
        """Trace each first-crash state before enumerating nested crashes."""
        label = f'crash:{point}'
        self.report['manifest'].append(label)
        self.report['expected'] += 1
        self.report['attempted'] += 1
        destination, original = self.prepare()
        initial = self.child(
            destination,
            fault={'index': point, 'kind': 'exit'},
        )
        _require_result(initial, crash=True)
        decision = journal_decision(
            destination, fallback=traced_decision(initial['events'])
        )
        recovery = self.child(destination, action='recover')
        _require_result(recovery)
        assert_recovered(
            destination, original, self.payload_root, decision=decision
        )
        self.recover(destination, original, decision)
        self.report['passed'] += 1
        self.report['cases'].append(label)
        self.report['recovery_events'][str(point)] = recovery['events']
        shutil.rmtree(destination)
        return list(recovery['events'])

    def schedule(
        self,
        cases: Sequence[tuple[str, dict[str, Any], int | None]],
    ) -> None:
        """Register the complete group before starting any group member."""
        self.report['expected'] += len(cases)
        self.report['manifest'].extend(label for label, _, _ in cases)
        self.save()
        for label, fault, first in cases:
            self.execute(label, fault, first)


def storage_cases(
    event: dict[str, Any],
) -> list[tuple[str, dict[str, Any], None]]:
    """Enumerate transient, persistent, and partial storage failures."""
    point = event['index']
    cases = []
    for number in (errno.ENOSPC, errno.EIO):
        base = {'index': point, 'kind': 'error', 'errno': number}
        cases.append((f'error:{point}:{number}', base, None))
        if event['edge'] != 'before':
            continue
        cases.append(
            (
                f'persistent:{point}:{number}',
                base | {'kind': 'persistent'},
                None,
            )
        )
        if event['operation'] in {'write_bytes', 'copy2'}:
            for fraction in (0, 0.5, 1):
                cases.append(
                    (
                        f'partial:{point}:{number}:{fraction}',
                        base | {'partial': fraction},
                        None,
                    )
                )
    return cases


def recovery_storage_points(events: list[dict[str, Any]]) -> set[int]:
    """Exercise every recovery phase with transient and persistent faults."""
    phases: dict[str, int] = {}
    for event in events:
        if event['edge'] == 'after' and event['phase'] is not None:
            phases.setdefault(event['phase'], event['index'])
    return set(phases.values())


def run_campaign(
    root: Path,
    payload_root: Path,
    *,
    existing: bool,
    copy_backups: bool,
    shard: int,
    shards: int,
    report_path: Path,
    verifier: ParquetVerifier,
) -> dict[str, Any]:
    """Visit every operation and every reachable recovery interruption."""
    campaign = Campaign(
        root,
        payload_root,
        report_path,
        existing=existing,
        copy_backups=copy_backups,
        shard=shard,
        shards=shards,
        verifier=verifier,
    )
    destination, original = campaign.prepare()
    baseline = campaign.child(destination)
    _require_result(baseline)
    assert_recovered(destination, original, payload_root, decision='new')
    verifier.verify(destination)
    campaign.report['initial_events'] = baseline['events']
    storage_points = recovery_storage_points(baseline['events'])
    shutil.rmtree(destination)
    campaign.save()
    for event in baseline['events']:
        point = event['index']
        if point % shards != shard:
            continue
        recovery_events = campaign.trace_recovery(point)
        nested_cases = [
            (
                f'nested:{point}:{item["index"]}',
                {'index': item['index'], 'kind': 'exit'},
                point,
            )
            for item in recovery_events
        ]
        campaign.schedule(nested_cases)
        if point in storage_points:
            for item in recovery_events:
                campaign.schedule(
                    [
                        (f'recovery-storage:{point}:{label}', fault, point)
                        for label, fault, _ in storage_cases(item)
                    ]
                )
        campaign.schedule(storage_cases(event))
        campaign.save()
    campaign.report['status'] = (
        'passed'
        if campaign.report['manifest'] == campaign.report['cases']
        and campaign.report['expected'] == campaign.report['passed']
        and campaign.report['attempted'] > 0
        else 'incomplete'
    )
    campaign.save()
    return campaign.report


def main() -> int:
    """Launch a single-threaded campaign outside pytest before forking."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('payload_root', type=Path)
    parser.add_argument('--existing', action='store_true')
    parser.add_argument('--copy-backups', action='store_true')
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.shard < args.shards:
        parser.error('shard must be in [0, shards)')
    with ParquetVerifier() as verifier:
        report = run_campaign(
            args.root,
            args.payload_root,
            existing=args.existing,
            copy_backups=args.copy_backups,
            shard=args.shard,
            shards=args.shards,
            report_path=args.report,
            verifier=verifier,
        )
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
