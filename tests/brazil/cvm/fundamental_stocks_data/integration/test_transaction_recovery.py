"""The first CVM extraction after an inspected crash must recover fully."""

from __future__ import annotations

import json
import socket
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    write_ownership,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_infra.transactional_publication import (
    TransactionalPublisher,
)
from scripts.process_runner import run_process
from tests.support.publication_crashes import CRASH_EXIT

pytestmark = pytest.mark.integration
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.parametrize('existing', [False, True])
def test_first_extraction_recovers_removed_transaction_directories(
    tmp_path: Path, existing: bool
) -> None:
    """Recovery reopens recreated directories and preserves caller bytes."""
    source = tmp_path / 'source.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', 'id;name\n1;first\n2;second\n')
    source_bytes = source.read_bytes()
    caller = tmp_path / 'caller.txt'
    caller.write_bytes(b'caller-owned bytes')
    if existing:
        (tmp_path / 'data.parquet').write_bytes(b'previous output')

    crashed = run_process(
        [
            'python',
            '-m',
            'tests.support.cvm_publication_crashes',
            str(source),
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert crashed.returncode == CRASH_EXIT, crashed.stderr
    outer_lock = tmp_path / write_ownership.LOCK_NAME
    owner = outer_lock / 'owner.json'
    record = json.loads(owner.read_text())
    assert record['hostname'] == socket.gethostname()
    assert TransactionalPublisher._pid_is_alive(record['pid']) is False
    assert sorted(path.name for path in outer_lock.iterdir()) == ['owner.json']
    owner.unlink()
    outer_lock.rmdir()

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '1', 'name': 'first'},
        {'id': '2', 'name': 'second'},
    ]
    assert source.read_bytes() == source_bytes
    assert caller.read_bytes() == b'caller-owned bytes'
    assert not outer_lock.exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction*'))
