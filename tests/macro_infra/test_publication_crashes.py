"""Process crashes, acquisition races, and private-state preservation."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
    TransactionalPublisher,
)
from globaldatafinance.macro_infra.transactional_publication.locking import (
    WINDOWS_GUARD_NAME,
)
from globaldatafinance.macro_infra.transactional_publication.manifests import (
    ManifestStore,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    LOCK_NAME,
    MANIFEST_PREFIX,
)
from scripts.process_runner import ProcessResult, run_process
from tests.support.publication_crashes import ARTIFACT_NAMES, CRASH_EXIT

pytestmark = pytest.mark.integration
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _worker(
    destination: Path, checkpoint: str, action: str = 'begin'
) -> ProcessResult:
    return run_process(
        [
            'python',
            '-m',
            'tests.support.publication_crashes',
            str(destination),
            checkpoint,
            action,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
    )


def _prepare(destination: Path, *, existing: bool) -> dict[str, bytes]:
    destination.mkdir()
    expected = {'caller.txt': b'caller-owned bytes'}
    if existing:
        expected.update(
            {name: b'old:' + name.encode() for name in ARTIFACT_NAMES}
        )
    for name, contents in expected.items():
        (destination / name).write_bytes(contents)
    if os.name == 'nt':
        expected[WINDOWS_GUARD_NAME] = b''
    return expected


def _files(destination: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in destination.iterdir()
        if path.is_file()
    }


@contextmanager
def _paused_writer(
    destination: Path, checkpoint: str, action: str = 'begin'
) -> Iterator[Path]:
    control = destination.parent / 'control'
    control.mkdir()
    with ThreadPoolExecutor(max_workers=1) as executor:
        writer = executor.submit(_worker, destination, checkpoint, action)
        try:
            deadline = time.monotonic() + 10
            while not (control / 'ready').exists():
                if writer.done() or time.monotonic() > deadline:
                    pytest.fail('Writer did not reach the controlled pause')
                time.sleep(0.01)
            yield control
        finally:
            (control / 'release').touch()
        completed = writer.result(timeout=10)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize(
    'checkpoint',
    [
        'lock_created',
        'owner_temporary_written',
        'owner_temporary_synced',
        'owner_published',
        'staging_created',
        'journal_temporary_written',
        'journal_published',
        'manifest_temporary_written',
        'manifest_published',
    ],
)
def test_restart_recovers_setup_crashes_without_residue(
    tmp_path: Path, checkpoint: str, existing: bool
) -> None:
    """Every setup interruption preserves caller bytes and permits retries."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=existing)

    crashed = _worker(destination, checkpoint)

    assert crashed.returncode == CRASH_EXIT, crashed.stderr
    for _attempt in range(3):
        publication = TransactionalPublisher(destination, owner='test').begin()
        publication.abort()
    assert _files(destination) == expected
    assert not any(path.is_dir() for path in destination.iterdir())


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize(
    ('checkpoint', 'committed'),
    [
        ('output_1_published', False),
        ('output_2_published', False),
        ('journal_committed', True),
        ('manifest_committed', True),
    ],
)
def test_commit_crash_recovers_one_complete_batch(
    tmp_path: Path, checkpoint: str, committed: bool, existing: bool
) -> None:
    """Crashes around the durable commit recover all old or all new bytes."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=existing)
    if committed:
        expected.update(
            {name: b'new:' + name.encode() for name in ARTIFACT_NAMES}
        )

    crashed = _worker(destination, checkpoint, 'commit')
    assert crashed.returncode == CRASH_EXIT, crashed.stderr
    publication = TransactionalPublisher(destination, owner='test').begin()
    publication.abort()

    assert _files(destination) == expected
    assert not any(path.is_dir() for path in destination.iterdir())


@pytest.mark.parametrize(
    'checkpoint',
    [
        'recovery_output_restored',
        'journal_rolled_back',
        'recovery_staging_removed',
        'recovery_lock_removed',
    ],
)
def test_restart_recovers_a_crash_during_recovery(
    tmp_path: Path, checkpoint: str
) -> None:
    """Interrupted rollback and cleanup remain safe to repeat."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=True)
    original = _worker(destination, 'output_1_published', 'commit')
    assert original.returncode == CRASH_EXIT, original.stderr

    recovery = _worker(destination, checkpoint, 'recover')
    assert recovery.returncode == CRASH_EXIT, recovery.stderr
    publication = TransactionalPublisher(destination, owner='test').begin()
    publication.abort()

    assert _files(destination) == expected
    assert not any(path.is_dir() for path in destination.iterdir())


def test_contender_preserves_a_live_lock_without_an_owner_record(
    tmp_path: Path,
) -> None:
    """A second process cannot reclaim a lock during its initialization."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=True)
    with _paused_writer(destination, 'pause_initialization'):
        lock = destination / LOCK_NAME
        identity = lock.stat().st_ino

        with pytest.raises(ExtractionError, match='another writer'):
            TransactionalPublisher(destination, owner='contender').begin()

        assert lock.stat().st_ino == identity
        assert not (lock / 'owner.json').exists()
    assert _files(destination) == expected
    assert not (destination / LOCK_NAME).exists()


@pytest.mark.parametrize(
    ('checkpoint', 'action', 'committed'),
    [
        ('pause_owned', 'begin', False),
        ('pause_publishing', 'commit', True),
        ('pause_recovery', 'recover', False),
    ],
)
def test_contenders_cannot_steal_live_publication_or_recovery(
    tmp_path: Path, checkpoint: str, action: str, committed: bool
) -> None:
    """Live owners and guarded recovery reject a second actual process."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=True)
    if action == 'recover':
        crashed = _worker(destination, 'output_1_published', 'commit')
        assert crashed.returncode == CRASH_EXIT, crashed.stderr

    with _paused_writer(destination, checkpoint, action) as control:
        pid = int((control / 'ready').read_text())
        assert TransactionalPublisher._pid_is_alive(pid) is True
        lock = destination / LOCK_NAME
        identity = lock.stat().st_ino
        owner = json.loads((lock / 'owner.json').read_text())
        if action != 'recover':
            assert owner['pid'] == pid

        with pytest.raises(ExtractionError, match=r'another writer|live PID'):
            TransactionalPublisher(destination, owner='contender').begin()

        assert lock.stat().st_ino == identity
        assert json.loads((lock / 'owner.json').read_text()) == owner

    assert TransactionalPublisher._pid_is_alive(pid) is False
    if committed:
        expected.update(
            {name: b'new:' + name.encode() for name in ARTIFACT_NAMES}
        )
    retry = TransactionalPublisher(destination, owner='contender').begin()
    retry.abort()
    assert _files(destination) == expected
    assert not (destination / LOCK_NAME).exists()


def test_incomplete_lock_with_unrecognized_contents_is_preserved(
    tmp_path: Path,
) -> None:
    """Missing ownership does not authorize removing caller-created entries."""
    lock = tmp_path / LOCK_NAME
    lock.mkdir(mode=0o700)
    caller = lock / 'caller.txt'
    caller.write_bytes(b'caller-owned contents')

    with pytest.raises(ExtractionError, match='unverifiable state'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert caller.read_bytes() == b'caller-owned contents'
    assert lock.is_dir()


def test_recovery_preserves_unowned_staging_and_manifest_temporaries(
    tmp_path: Path,
) -> None:
    """Legacy residues without private authority cannot be deleted by name."""
    prefix = f'{MANIFEST_PREFIX}{"a" * 32}'
    staging = tmp_path / f'{prefix}-caller'
    staging.mkdir(mode=0o700)
    caller = staging / 'keep.txt'
    caller.write_bytes(b'caller-owned directory')
    temporary = tmp_path / f'{prefix}.json-{"b" * 32}.tmp'
    temporary.write_bytes(b'caller-owned temporary name')
    temporary.chmod(0o600)

    publication = TransactionalPublisher(tmp_path, owner='test').begin()
    publication.abort()

    assert caller.read_bytes() == b'caller-owned directory'
    assert temporary.read_bytes() == b'caller-owned temporary name'


@pytest.mark.parametrize('discovery', [False, True])
def test_previous_layout_journal_remains_recoverable(
    tmp_path: Path, discovery: bool
) -> None:
    """Private journals in the previous layout retain their authority."""
    destination = tmp_path / 'destination'
    expected = _prepare(destination, existing=True)
    crashed = _worker(destination, 'output_1_published', 'commit')
    assert crashed.returncode == CRASH_EXIT, crashed.stderr
    manifest_path = next(destination.glob(f'{MANIFEST_PREFIX}*.json'))
    store = ManifestStore(destination, str(destination), FileOperations())
    manifest = store.read(manifest_path)
    nested = manifest.staging_dir
    legacy = destination / nested.name
    nested.rename(legacy)
    manifest.staging_dir = legacy
    for artifact in manifest.artifacts:
        artifact.staged_path = legacy / artifact.staged_path.relative_to(
            nested
        )
        if artifact.backup_path is not None:
            artifact.backup_path = legacy / artifact.backup_path.relative_to(
                nested
            )
    store.write(manifest, manifest_path)
    if not discovery:
        manifest_path.unlink()

    publication = TransactionalPublisher(destination, owner='test').begin()
    publication.abort()

    assert _files(destination) == expected
    assert not any(path.is_dir() for path in destination.iterdir())


@pytest.mark.parametrize('alias', ['symlink', 'hardlink'])
def test_initial_ownership_temporary_cannot_alias_caller_data(
    tmp_path: Path, alias: str
) -> None:
    """A matching temporary name never authorizes following caller aliases."""
    caller = tmp_path / 'caller.json'
    caller.write_bytes(b'caller-owned bytes')
    caller.chmod(0o600)
    lock = tmp_path / LOCK_NAME
    lock.mkdir(mode=0o700)
    temporary = lock / f'owner.json-{"a" * 32}.tmp'
    if alias == 'symlink':
        try:
            temporary.symlink_to(caller)
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                pytest.skip(
                    'Windows symlink capability unavailable: error 1314'
                )
            raise
    else:
        temporary.hardlink_to(caller)

    with pytest.raises(ExtractionError, match='Recovery state'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert caller.read_bytes() == b'caller-owned bytes'
    assert temporary.exists()
