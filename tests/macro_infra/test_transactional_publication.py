"""Failure-atomic publication regressions shared by CVM and B3."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from globaldatafinance.macro_exceptions import DiskFullError, ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
    TransactionalPublication,
    TransactionalPublisher,
)

pytestmark = pytest.mark.integration


def _stage_artifact(
    publisher: TransactionalPublisher,
    name: str,
    contents: bytes,
) -> tuple[TransactionalPublication, Path]:
    """Create and register one already-validated test artifact."""
    publication = publisher.begin()
    staged = publication.stage_path(name)
    staged.write_bytes(contents)
    publication.add_artifact(
        final_path=publisher.destination_dir / name,
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='schema-v1',
    )
    return publication, staged


class _FailSecondPublicationReplace(FileOperations):
    """Fail exactly the second staged Parquet replacement, then recover."""

    def __init__(self) -> None:
        self.publications = 0

    def replace(self, source: Path, destination: Path) -> None:
        """Inject a failure only while staging the second public artifact."""
        if source.parent.name != 'backups' and source.suffix == '.parquet':
            self.publications += 1
            if self.publications == 2:
                raise OSError('injected second publication rename failure')
        super().replace(source, destination)


class _NoBackupSpaceOperations(FileOperations):
    """Force the portable-copy backup capacity check to reject commit."""

    def disk_free_bytes(self, path: Path) -> int:
        """Report a full filesystem without changing the real test volume."""
        _ = path
        return 0


class _FailManifestWriteOperations(FileOperations):
    """Fail the first transaction-manifest write after staging exists."""

    def write_bytes(self, path: Path, payload: bytes) -> None:
        """Leave lock writes available while rejecting manifest persistence."""
        if path.name.startswith('.globaldatafinance-transaction-'):
            raise OSError('injected manifest write failure')
        super().write_bytes(path, payload)


class _FailRollbackOperations(FileOperations):
    """Leave recovery evidence when the first rollback restore fails."""

    def __init__(self) -> None:
        self.publications = 0
        self.fail_restore = True

    def replace(self, source: Path, destination: Path) -> None:
        """Fail one publication and one immediate backup restoration."""
        if source.parent.name != 'backups' and source.suffix == '.parquet':
            self.publications += 1
            if self.publications == 2:
                raise OSError('injected publication failure')
        if source.parent.name == 'backups' and self.fail_restore:
            self.fail_restore = False
            raise OSError('injected rollback restore failure')
        super().replace(source, destination)


class _FailCleanupOperations(FileOperations):
    """Fail cleanup after a durable commit without changing final output."""

    def __init__(self) -> None:
        self.failed = False

    def rmtree(self, path: Path) -> None:
        """Leave the staging directory for the next recovery attempt."""
        if not self.failed:
            self.failed = True
            raise OSError('injected cleanup failure')
        super().rmtree(path)


def _register(
    publication: TransactionalPublication,
    destination: Path,
    name: str,
    contents: bytes,
) -> None:
    """Write and register one artifact through the public transaction API."""
    staged = publication.stage_path(name)
    staged.write_bytes(contents)
    publication.add_artifact(
        final_path=destination / name,
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='schema-v1',
    )


def test_destination_validation_has_no_transaction_side_effects(
    tmp_path: Path,
) -> None:
    """Preflight validates only and does not initialize manifest state."""
    publisher = TransactionalPublisher(tmp_path, owner='test')

    publisher.validate_destination()

    assert publisher._manifest_store is None
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_commit_replaces_outputs_and_removes_all_transaction_state(
    tmp_path: Path,
) -> None:
    """A complete transaction leaves only the validated final output."""
    final = tmp_path / 'quotes.parquet'
    final.write_bytes(b'old output')
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication, _ = _stage_artifact(publisher, final.name, b'new output')

    publication.mark_validated()
    publication.commit()

    assert final.read_bytes() == b'new output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()


def test_second_rename_failure_restores_every_preexisting_output(
    tmp_path: Path,
) -> None:
    """A multi-artifact failure never exposes a partly committed CVM batch."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    first.write_bytes(b'old first')
    second.write_bytes(b'old second')
    publisher = TransactionalPublisher(
        tmp_path,
        owner='test',
        operations=_FailSecondPublicationReplace(),
    )
    publication = publisher.begin()
    _register(publication, tmp_path, first.name, b'new first')
    _register(publication, tmp_path, second.name, b'new second')
    publication.mark_validated()

    with pytest.raises(
        ExtractionError, match='all modified outputs were restored'
    ):
        publication.commit()

    assert first.read_bytes() == b'old first'
    assert second.read_bytes() == b'old second'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()


def test_validated_commit_requires_capacity_for_copy_based_backups(
    tmp_path: Path,
) -> None:
    """Reject a commit before replacing an old output on no-space errors."""
    final = tmp_path / 'quotes.parquet'
    final.write_bytes(b'old output')
    publisher = TransactionalPublisher(
        tmp_path,
        owner='test',
        operations=_NoBackupSpaceOperations(),
    )
    publication, _ = _stage_artifact(publisher, final.name, b'new output')

    with pytest.raises(DiskFullError):
        publication.mark_validated()
    publication.abort()

    assert final.read_bytes() == b'old output'


def test_initial_manifest_write_failure_cleans_private_staging_and_lock(
    tmp_path: Path,
) -> None:
    """An interrupted transaction setup leaves no orphaned derived state."""
    publisher = TransactionalPublisher(
        tmp_path,
        owner='test',
        operations=_FailManifestWriteOperations(),
    )

    with pytest.raises(OSError, match='manifest write failure'):
        publisher.begin()

    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()


def test_recovery_restores_an_interrupted_publishing_manifest(
    tmp_path: Path,
) -> None:
    """The next invocation recovers a dead process before taking its lock."""
    final = tmp_path / 'quotes.parquet'
    final.write_bytes(b'old output')
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication, staged = _stage_artifact(publisher, final.name, b'new output')
    publication.mark_validated()
    publication._prepare_backups()
    publication.manifest.phase = 'PUBLISHING'
    publisher._write_manifest(publication.manifest, publication.manifest_path)
    publisher.operations.replace(staged, final)
    publication.manifest.artifacts[0].published = True
    publisher._write_manifest(publication.manifest, publication.manifest_path)

    lock_owner = (
        tmp_path / '.globaldatafinance-transaction.lock' / 'owner.json'
    )
    lock_owner.write_text(
        json.dumps(
            {
                'hostname': socket.gethostname(),
                'pid': 99_999_999,
                'transaction_id': publication.manifest.transaction_id,
                'manifest': publication.manifest_path.name,
            }
        ),
        encoding='utf-8',
    )

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    assert final.read_bytes() == b'old output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()


def test_existing_live_lock_is_rejected_without_mutating_its_artifacts(
    tmp_path: Path,
) -> None:
    """Reject a concurrent local writer rather than overwriting it silently."""
    lock_dir = tmp_path / '.globaldatafinance-transaction.lock'
    lock_dir.mkdir()
    owner = lock_dir / 'owner.json'
    owner.write_text(
        json.dumps(
            {
                'hostname': socket.gethostname(),
                'pid': os.getpid(),
                'transaction_id': 'live',
                'manifest': 'missing.json',
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ExtractionError, match='live PID'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert owner.exists()


def test_dead_lock_without_manifest_is_recovered_safely(
    tmp_path: Path,
) -> None:
    """A crash before manifest persistence does not block output forever."""
    lock_dir = tmp_path / '.globaldatafinance-transaction.lock'
    lock_dir.mkdir()
    owner = lock_dir / 'owner.json'
    owner.write_text(
        json.dumps(
            {
                'hostname': socket.gethostname(),
                'pid': 99_999_999,
                'transaction_id': '',
                'manifest': '',
            }
        ),
        encoding='utf-8',
    )
    orphan = tmp_path / (
        '.globaldatafinance-transaction-'
        '0123456789abcdef0123456789abcdef-orphan'
    )
    orphan.mkdir()
    (orphan / 'derived.tmp').write_bytes(b'derived')

    publication = TransactionalPublisher(tmp_path, owner='test').begin()
    publication.abort()

    assert not lock_dir.exists()
    assert not orphan.exists()


def test_failed_rollback_preserves_manifest_until_next_invocation(
    tmp_path: Path,
) -> None:
    """A restore failure never discards evidence needed for recovery."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    first.write_bytes(b'old first')
    second.write_bytes(b'old second')
    publisher = TransactionalPublisher(
        tmp_path,
        owner='test',
        operations=_FailRollbackOperations(),
    )
    publication = publisher.begin()
    _register(publication, tmp_path, first.name, b'new first')
    _register(publication, tmp_path, second.name, b'new second')
    publication.mark_validated()

    with pytest.raises(ExtractionError, match='rollback failures'):
        publication.commit()

    manifests = list(tmp_path.glob('.globaldatafinance-transaction-*.json'))
    assert len(manifests) == 1
    lock_owner = (
        tmp_path / '.globaldatafinance-transaction.lock' / 'owner.json'
    )
    record = json.loads(lock_owner.read_text(encoding='utf-8'))
    record['pid'] = 99_999_999
    lock_owner.write_text(json.dumps(record), encoding='utf-8')

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    assert first.read_bytes() == b'old first'
    assert second.read_bytes() == b'old second'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_cleanup_failure_keeps_durable_commit_recoverable(
    tmp_path: Path,
) -> None:
    """A cleanup interruption preserves the newly committed output."""
    final = tmp_path / 'quotes.parquet'
    publisher = TransactionalPublisher(
        tmp_path,
        owner='test',
        operations=_FailCleanupOperations(),
    )
    publication, _ = _stage_artifact(publisher, final.name, b'new output')
    publication.mark_validated()

    with pytest.raises(ExtractionError, match='cleanup is pending'):
        publication.commit()

    assert final.read_bytes() == b'new output'
    assert list(tmp_path.glob('.globaldatafinance-transaction-*.json'))
    lock_owner = (
        tmp_path / '.globaldatafinance-transaction.lock' / 'owner.json'
    )
    record = json.loads(lock_owner.read_text(encoding='utf-8'))
    record['pid'] = 99_999_999
    lock_owner.write_text(json.dumps(record), encoding='utf-8')

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    assert final.read_bytes() == b'new output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_stage_path_cannot_escape_transaction_staging(tmp_path: Path) -> None:
    """Untrusted artifact names never become arbitrary filesystem targets."""
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()

    with pytest.raises(ExtractionError, match='Unsafe staged artifact name'):
        publication.stage_path('../outside.parquet')
    publication.abort()


def test_manifest_cannot_treat_destination_as_staging_directory(
    tmp_path: Path,
) -> None:
    """Recovery rejects a manifest that could delete the destination root."""
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()
    staged = publication.stage_path('quotes.parquet')
    staged.write_bytes(b'new output')
    publication.add_artifact(
        final_path=tmp_path / 'quotes.parquet',
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='schema-v1',
    )
    payload = json.loads(publication.manifest_path.read_text(encoding='utf-8'))
    payload['staging_dir'] = '.'
    publication.manifest_path.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ExtractionError, match='Path must name an artifact'):
        publisher._read_manifest(publication.manifest_path)

    assert tmp_path.is_dir()
    assert staged.exists()
    publication.abort()
