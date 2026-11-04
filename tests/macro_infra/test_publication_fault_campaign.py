"""Complete opt-in Linux campaign over publication and recovery operations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.process_runner import run_process
from tests.support.publication_crashes import ARTIFACT_NAMES

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        sys.platform != 'linux',
        reason='the complete fork/descriptor campaign runs on native Linux',
    ),
]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('copy_backups', [False, True])
def test_complete_publication_fault_campaign(
    tmp_path: Path, existing: bool, copy_backups: bool
) -> None:
    """Every reached boundary preserves caller bytes and a complete batch."""
    payload_root = tmp_path / 'payloads'
    payload_root.mkdir()
    for version, rows in [('old', 1), ('new', 2)]:
        for name in ARTIFACT_NAMES:
            table = pa.table(
                {'version': [version] * rows, 'item': [name] * rows}
            )
            path = payload_root / f'{version}-{name}'
            pq.write_table(table, path)
            assert pq.read_table(path).equals(table)
    shard = int(os.environ.get('GDF_PUBLICATION_SHARD', '0'))
    shards = int(os.environ.get('GDF_PUBLICATION_SHARDS', '1'))
    reports = Path(os.environ.get('GDF_PUBLICATION_REPORT_DIR', str(tmp_path)))
    report_path = (
        reports / f'campaign-{int(existing)}-{int(copy_backups)}-{shard}.json'
    )
    command = [
        'python',
        '-m',
        'tests.support.publication_campaign',
        str(tmp_path / 'campaign'),
        str(payload_root),
        '--shard',
        str(shard),
        '--shards',
        str(shards),
        '--report',
        str(report_path),
    ]
    if existing:
        command.append('--existing')
    if copy_backups:
        command.append('--copy-backups')

    result = run_process(command, cwd=REPOSITORY_ROOT, check=False)

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text())
    assert report['status'] == 'passed'
    assert report['expected'] == report['attempted'] == report['passed'] > 0
    assert report['failures'] == []
