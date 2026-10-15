"""Platform policies must preserve process ownership and permission errors."""

from __future__ import annotations

import errno
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
    TransactionalPublisher,
    durability,
)
from globaldatafinance.macro_infra.transactional_publication import (
    types as publication_types,
)


@pytest.mark.integration
def test_live_process_query_never_sends_a_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Querying the current writer cannot deliver a console event or signal."""
    signal = Mock(side_effect=AssertionError('process query sent a signal'))
    monkeypatch.setattr(os, 'kill', signal)

    assert TransactionalPublisher._pid_is_alive(os.getpid()) is True
    signal.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize('alive', [True, False])
def test_process_query_retains_the_operating_system_result(
    monkeypatch: pytest.MonkeyPatch, alive: bool
) -> None:
    """An exited process cannot keep a transaction locked indefinitely."""
    process = Mock()
    process.is_running.return_value = alive
    monkeypatch.setattr(psutil, 'Process', Mock(return_value=process))

    assert TransactionalPublisher._pid_is_alive(1234) is alive


@pytest.mark.unit
def test_missing_process_allows_stale_lock_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exit during process construction is also treated as stale."""
    monkeypatch.setattr(
        psutil, 'Process', Mock(side_effect=psutil.NoSuchProcess(1234))
    )

    assert TransactionalPublisher._pid_is_alive(1234) is False


@pytest.mark.unit
def test_unverifiable_process_retains_the_diagnostic_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Denied process access cannot authorize reclaiming another writer."""
    denied = psutil.AccessDenied(1234)
    monkeypatch.setattr(psutil, 'Process', Mock(side_effect=denied))

    with pytest.raises(ExtractionError, match='Cannot verify') as failure:
        TransactionalPublisher._pid_is_alive(1234)

    assert failure.value.__cause__ is denied


@pytest.mark.integration
def test_windows_directory_sync_policy_allows_a_complete_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsupported CRT directory opens cannot prevent transaction startup."""
    monkeypatch.setattr(
        publication_types,
        'sys',
        SimpleNamespace(platform='win32'),
        raising=False,
    )
    original_open = os.open
    original_fsync = os.fsync

    def windows_open(path: Path, flags: int, mode: int = 0o777) -> int:
        if path.is_dir():
            raise PermissionError(errno.EACCES, 'CRT directory open denied')
        return original_open(path, flags, mode)

    def windows_fsync(descriptor: int) -> None:
        os.write(descriptor, b'')
        original_fsync(descriptor)

    monkeypatch.setattr(
        publication_types,
        'os',
        SimpleNamespace(
            **(vars(os) | {'open': windows_open, 'fsync': windows_fsync})
        ),
    )
    operations = FileOperations()
    with pytest.raises(OSError) as unsupported:
        operations.fsync_directory(tmp_path)
    assert unsupported.value.errno == errno.ENOTSUP

    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()
    staged = publication.stage_path('data.parquet')
    staged.write_bytes(b'new output')
    publication.add_artifact(
        final_path=tmp_path / 'data.parquet',
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='test-v1',
    )
    publication.mark_validated()
    publication.commit()

    assert (tmp_path / 'data.parquet').read_bytes() == b'new output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction*'))


@pytest.mark.integration
@pytest.mark.parametrize(
    'error_number', [errno.EACCES, errno.EPERM, errno.EIO]
)
def test_supported_platform_directory_sync_preserves_real_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """Permission and disk failures on supported platforms still propagate."""
    failure = OSError(error_number, 'injected directory failure')
    monkeypatch.setattr(
        publication_types,
        'sys',
        SimpleNamespace(platform='linux'),
        raising=False,
    )
    monkeypatch.setattr(
        publication_types.os, 'open', Mock(side_effect=failure)
    )

    with pytest.raises(OSError) as raised:
        durability.sync_directory(FileOperations(), tmp_path)

    assert raised.value is failure
