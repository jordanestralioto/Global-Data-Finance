"""Recovery distinguishes a transaction owner from a reused process ID."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    TransactionalPublisher,
)


@pytest.mark.integration
def test_reused_pid_recovers_the_previous_complete_output(
    tmp_path: Path,
) -> None:
    """PID reuse must still restore an interrupted publication's backup."""
    final = tmp_path / 'quotes.parquet'
    final.write_bytes(b'previous complete output')
    caller_file = tmp_path / 'caller.txt'
    caller_file.write_bytes(b'caller data')
    publisher = TransactionalPublisher(tmp_path, owner='test')
    interrupted = publisher.begin()
    staged = interrupted.stage_path(final.name)
    staged.write_bytes(b'new complete output')
    interrupted.add_artifact(
        final_path=final,
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='test-v1',
    )
    interrupted.mark_validated()
    interrupted._prepare_backups()
    interrupted.manifest.phase = 'PUBLISHING'
    publisher._write_manifest(interrupted.manifest, interrupted.manifest_path)
    publisher.operations.replace(staged, final)
    interrupted.manifest.artifacts[0].published = True
    publisher._write_manifest(interrupted.manifest, interrupted.manifest_path)
    owner_path = publisher.lock_dir / 'owner.json'
    record = json.loads(owner_path.read_text(encoding='utf-8'))
    record['process_started_at'] = (
        psutil.Process(os.getpid()).create_time() - 60
    )
    owner_path.write_text(json.dumps(record), encoding='utf-8')

    resumed = TransactionalPublisher(tmp_path, owner='test').begin()
    resumed.abort()

    assert final.read_bytes() == b'previous complete output'
    assert caller_file.read_bytes() == b'caller data'
    assert not publisher.lock_dir.exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.integration
def test_live_owner_records_and_checks_the_process_start_time(
    tmp_path: Path,
) -> None:
    """Another invocation cannot reclaim the same live process instance."""
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()
    owner_path = publisher.lock_dir / 'owner.json'
    try:
        before = owner_path.read_bytes()
        record = json.loads(before)
        assert record['process_started_at'] == (
            psutil.Process(os.getpid()).create_time()
        )

        with pytest.raises(ExtractionError, match='live PID'):
            TransactionalPublisher(tmp_path, owner='test').begin()

        assert owner_path.read_bytes() == before
        assert publication.manifest_path.exists()
    finally:
        publication.abort()


@pytest.mark.integration
@pytest.mark.parametrize(
    'invalid_start',
    [None, True, 'invalid', -1, 0, float('inf'), float('nan'), 10**309],
)
def test_invalid_owner_start_time_cannot_authorize_recovery(
    tmp_path: Path, invalid_start: object
) -> None:
    """A malformed identity is preserved for explicit operator inspection."""
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()
    owner_path = publisher.lock_dir / 'owner.json'
    record = json.loads(owner_path.read_text(encoding='utf-8'))
    record['process_started_at'] = invalid_start
    owner_path.write_text(json.dumps(record), encoding='utf-8')
    before = owner_path.read_bytes()
    try:
        with pytest.raises(ExtractionError, match='process start time'):
            TransactionalPublisher(tmp_path, owner='test').begin()

        assert owner_path.read_bytes() == before
        assert publication.manifest_path.exists()
    finally:
        publication.abort()


@pytest.mark.unit
@pytest.mark.parametrize('same_process', [True, False])
def test_process_query_compares_the_recorded_start_time(
    monkeypatch: pytest.MonkeyPatch, same_process: bool
) -> None:
    """An existing PID is insufficient evidence of the previous owner."""
    process = Mock()
    process.is_running.return_value = True
    process.create_time.return_value = 100 if same_process else 200
    monkeypatch.setattr(psutil, 'Process', Mock(return_value=process))

    assert (
        TransactionalPublisher._pid_is_alive(1234, started_at=100)
        is same_process
    )


@pytest.mark.unit
@pytest.mark.parametrize('query_error', ['missing', 'denied'])
def test_process_identity_query_handles_exit_and_permission_failures(
    monkeypatch: pytest.MonkeyPatch, query_error: str
) -> None:
    """A vanished process is stale; an unverifiable process stays locked."""
    error = (
        psutil.NoSuchProcess(1234)
        if query_error == 'missing'
        else psutil.AccessDenied(1234)
    )
    process = Mock()
    process.is_running.return_value = True
    process.create_time.side_effect = error
    monkeypatch.setattr(psutil, 'Process', Mock(return_value=process))

    if query_error == 'missing':
        assert not TransactionalPublisher._pid_is_alive(1234, started_at=100)
    else:
        with pytest.raises(ExtractionError, match='Cannot verify') as failure:
            TransactionalPublisher._pid_is_alive(1234, started_at=100)
        assert failure.value.__cause__ is error
