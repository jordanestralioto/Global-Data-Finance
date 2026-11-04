"""Create deterministic distribution and release evidence test fixtures."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from scripts.check_distributions import REQUIRED_MODULES, inspect_distributions
from scripts.check_release_evidence import NATIVE_REQUIRED_CASES
from tests.support.publication_campaign import (
    recovery_storage_points,
    storage_cases,
)


def build_distributions(
    root: Path,
    *,
    wheel_version: str = '0.2.0',
    source_version: str = '0.2.0',
    missing: str | None = None,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    wheel = root / 'globaldatafinance-0.2.0-py3-none-any.whl'
    source = root / 'globaldatafinance-0.2.0.tar.gz'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr(
            'globaldatafinance-0.2.0.dist-info/METADATA',
            f'Name: globaldatafinance\nVersion: {wheel_version}\n'
            'Requires-Python: <4.0,>=3.12\n',
        )
        for module in REQUIRED_MODULES:
            if module != missing:
                archive.writestr(module, b'')
    with tarfile.open(source, 'w:gz') as archive:
        entries = {
            'globaldatafinance-0.2.0/PKG-INFO': (
                f'Name: globaldatafinance\nVersion: {source_version}\n'
                'Requires-Python: >=3.12,<4.0\n'
            ).encode()
        }
        entries.update(
            {
                f'globaldatafinance-0.2.0/src/{module}': b''
                for module in REQUIRED_MODULES
                if module != missing
            }
        )
        for name, contents in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            archive.addfile(member, io.BytesIO(contents))
    return wheel, source


def campaign_report(
    existing: bool = False,
    copy_backups: bool = False,
    *,
    shard: int = 0,
    shards: int = 1,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = [
        {'index': 0, 'operation': 'mkdir', 'edge': 'before', 'phase': None},
        {
            'index': 1,
            'operation': 'write_bytes',
            'edge': 'after',
            'phase': 'OPEN',
        },
        {
            'index': 2,
            'operation': 'write_bytes',
            'edge': 'before',
            'phase': 'OPEN',
        },
    ]
    if shards != 1:
        events = [events[0] | {'index': index} for index in range(shards)]
    selected = [event for event in events if event['index'] % shards == shard]
    recovery = [
        {
            'index': 0,
            'operation': 'cleanup.unlink',
            'edge': 'before',
            'phase': 'OPEN',
        }
    ]
    labels = []
    for event in selected:
        point = event['index']
        labels.extend([f'crash:{point}', f'nested:{point}:0'])
        labels.extend(label for label, _, _ in storage_cases(event))
        if point in recovery_storage_points(events):
            labels.extend(
                f'recovery-storage:{point}:{label}'
                for label, _, _ in storage_cases(recovery[0])
            )
    return {
        'scenario': {'existing': existing, 'copy_backups': copy_backups},
        'shard': shard,
        'shards': shards,
        'status': 'passed',
        'failures': [],
        'initial_events': events,
        'recovery_events': {str(item['index']): recovery for item in selected},
        'manifest': labels.copy(),
        'cases': labels,
        'expected': len(labels),
        'attempted': len(labels),
        'passed': len(labels),
    }


def native_reports(tmp_path: Path) -> list[Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for system in ('Windows', 'Darwin'):
        for version in ('3.12', '3.13', '3.14'):
            collected = [
                f'tests/native.py::{name}' for name in NATIVE_REQUIRED_CASES
            ]
            report = {
                'system': system,
                'python': version + '.1',
                'status': 'passed',
                'exit_code': 0,
                'issues': [],
                'collected': collected,
                'outcomes': dict.fromkeys(collected, 'passed'),
            }
            path = tmp_path / f'{system}-{version}.json'
            path.write_text(json.dumps(report))
            paths.append(path)
    return paths


def acceptance_bundle(root: Path, sha: str) -> None:
    """Build synthetic artifacts for verifier tests, without running CI."""
    for source in native_reports(root / 'native-fixtures'):
        report = json.loads(source.read_text())
        destination = root / f'native-{source.stem}'
        destination.mkdir()
        (destination / 'results.json').write_text(json.dumps(report))
        (destination / 'environment.txt').write_text(sha + '\n')
        (destination / 'junit.xml').write_text('<testsuites/>')
    for shard in range(8):
        destination = root / f'publication-campaign-{shard}'
        reports = destination / 'reports'
        reports.mkdir(parents=True)
        (destination / 'environment.txt').write_text(sha + '\n')
        for existing in (False, True):
            for copy_backups in (False, True):
                report = campaign_report(
                    existing, copy_backups, shard=shard, shards=8
                )
                scenario = f'{int(existing)}-{int(copy_backups)}'
                filename = f'campaign-{scenario}-{shard}.json'
                (reports / filename).write_text(json.dumps(report))
    build_distributions(root / 'dist-packages')
    package = root / 'release-package-evidence'
    package.mkdir()
    (package / 'distributions.json').write_text(
        json.dumps(inspect_distributions(root / 'dist-packages', '0.2.0'))
    )
    for kind in ('wheel', 'sdist'):
        (package / f'smoke-{kind}.status').write_text('passed\n')
        (package / f'smoke-{kind}.log').write_text('')
    for version in ('3.12', '3.13', '3.14'):
        directory = root / f'coverage-report-py{version}'
        directory.mkdir()
        (directory / 'environment.txt').write_text(sha + '\n')
        report = {
            'meta': {'branch_coverage': True},
            'totals': {
                'num_statements': 100,
                'num_branches': 20,
                'percent_covered': 90.0,
            },
        }
        for kind in ('product', 'executor'):
            (directory / f'{kind}.json').write_text(json.dumps(report))
