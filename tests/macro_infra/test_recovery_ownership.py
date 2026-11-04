"""Private recovery authority and caller-data preservation regressions."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
    TransactionalPublication,
    TransactionalPublisher,
    cleanup,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    JOURNAL_NAME,
    LOCK_NAME,
    MANIFEST_PREFIX,
)

pytestmark = pytest.mark.integration


def _registered_publication(
    destination: Path,
) -> tuple[TransactionalPublisher, TransactionalPublication, Path]:
    """Create real private recovery state for an existing output."""
    final = destination / 'quotes.parquet'
    final.write_bytes(b'previous output')
    publisher = TransactionalPublisher(destination, owner='test')
    publication = publisher.begin()
    staged = publication.stage_path(final.name)
    staged.write_bytes(b'new output')
    publication.add_artifact(
        final_path=final,
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='schema-v1',
    )
    return publisher, publication, final


def _mark_process_dead(destination: Path) -> None:
    """Simulate restart without replacing the private lock inode."""
    path = destination / LOCK_NAME / 'owner.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['pid'] = 99_999_999
    path.write_text(json.dumps(payload), encoding='utf-8')


@pytest.mark.parametrize('phase', ['OPEN', 'PUBLISHING', 'CLEANUP_PENDING'])
def test_correct_names_and_permissions_cannot_replace_private_authority(
    tmp_path: Path, phase: str
) -> None:
    """A plausible external record still cannot authorize caller deletion."""
    caller_source = tmp_path / 'source.txt'
    caller_source.write_bytes(b'caller-owned source')
    transaction_id = 'b' * 32
    staging = tmp_path / f'{MANIFEST_PREFIX}{transaction_id}-pretend'
    staging.mkdir(mode=0o700)
    keep = staging / 'keep.txt'
    keep.write_bytes(b'caller-owned directory contents')
    path = tmp_path / f'{MANIFEST_PREFIX}{transaction_id}.json'
    path.write_text(
        json.dumps(
            {
                'version': 2,
                'transaction_id': transaction_id,
                'owner': 'test',
                'staging_dir': staging.name,
                'created_at': '2026-10-14T00:00:00+00:00',
                'phase': phase,
                'artifacts': [
                    {
                        'final_path': caller_source.name,
                        'staged_path': f'{staging.name}/new.parquet',
                        'schema_fingerprint': 'schema-v1',
                        'expected_rows': 1,
                        'publishing': phase == 'PUBLISHING',
                        'publication_identity': [1, 2, 3, 4],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    path.chmod(0o600)

    with pytest.raises(ExtractionError, match='private recovery state'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert caller_source.read_bytes() == b'caller-owned source'
    assert keep.read_bytes() == b'caller-owned directory contents'
    assert path.is_file()
    assert not (tmp_path / LOCK_NAME).exists()


def test_tampered_discovery_flags_cannot_authorize_source_deletion(
    tmp_path: Path,
) -> None:
    """Only the authentic private artifact inventory drives recovery."""
    _publisher, publication, final = _registered_publication(tmp_path)
    caller_source = tmp_path / 'source.txt'
    caller_source.write_bytes(b'caller-owned source')
    payload = json.loads(publication.manifest_path.read_text())
    payload['phase'] = 'PUBLISHING'
    payload['artifacts'][0]['final_path'] = caller_source.name
    payload['artifacts'][0]['publishing'] = True
    publication.manifest_path.write_text(json.dumps(payload))
    _mark_process_dead(tmp_path)

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    assert caller_source.read_bytes() == b'caller-owned source'
    assert final.read_bytes() == b'previous output'
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        final.name,
        caller_source.name,
    ]


@pytest.mark.parametrize('discovery', ['missing', 'stale'])
def test_private_publishing_journal_recovers_after_discovery_interruption(
    tmp_path: Path, discovery: str
) -> None:
    """Journal durability precedes every externally visible update."""
    publisher, publication, final = _registered_publication(tmp_path)
    old_discovery = publication.manifest_path.read_bytes()
    publication.mark_validated()
    publication._prepare_backups()
    publication.manifest.phase = 'PUBLISHING'
    publication.manifest.artifacts[0].publishing = True
    publisher._write_manifest(publication.manifest, publication.manifest_path)
    publisher.operations.replace(
        publication.manifest.artifacts[0].staged_path, final
    )
    if discovery == 'missing':
        publication.manifest_path.unlink()
    else:
        publication.manifest_path.write_bytes(old_discovery)
    _mark_process_dead(tmp_path)

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    assert final.read_bytes() == b'previous output'
    assert list(tmp_path.iterdir()) == [final]


@pytest.mark.parametrize('target', ['staging', 'journal', 'lock'])
def test_nonprivate_recovery_state_is_rejected_before_mutation(
    tmp_path: Path, target: str
) -> None:
    """A shared journal or transaction directory provides no authority."""
    if not hasattr(os, 'geteuid'):
        pytest.skip('POSIX ownership and permission contract')
    _publisher, publication, final = _registered_publication(tmp_path)
    _mark_process_dead(tmp_path)
    path = {
        'staging': publication.staging_dir,
        'journal': publication.staging_dir / JOURNAL_NAME,
        'lock': tmp_path / LOCK_NAME,
    }[target]
    path.chmod(0o755 if path.is_dir() else 0o644)

    with pytest.raises(ExtractionError, match='private filesystem ownership'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert final.read_bytes() == b'previous output'
    assert publication.manifest_path.is_file()
    assert (publication.staging_dir / final.name).read_bytes() == b'new output'


@pytest.mark.parametrize('target', ['manifest', 'journal', 'lock'])
def test_recovery_rejects_symlinked_state_and_preserves_link_targets(
    tmp_path: Path, target: str
) -> None:
    """Discovery and lock aliases never confer private directory ownership."""
    _publisher, publication, final = _registered_publication(tmp_path)
    _mark_process_dead(tmp_path)
    path = {
        'manifest': publication.manifest_path,
        'journal': publication.staging_dir / JOURNAL_NAME,
        'lock': tmp_path / LOCK_NAME / 'owner.json',
    }[target]
    preserved = tmp_path / 'caller-record.json'
    preserved.write_bytes(path.read_bytes())
    before = preserved.read_bytes()
    path.unlink()
    path.symlink_to(preserved)

    with pytest.raises(ExtractionError, match='unsafe type'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert final.read_bytes() == b'previous output'
    assert preserved.read_bytes() == before
    assert path.is_symlink()


def test_private_journal_is_bound_to_original_directory_identity(
    tmp_path: Path,
) -> None:
    """Copied state cannot authorize cleanup in a different directory."""
    _publisher, publication, final = _registered_publication(tmp_path)
    path = publication.staging_dir / JOURNAL_NAME
    payload = json.loads(path.read_text())
    payload['destination_identity'] = [0, 0]
    path.write_text(json.dumps(payload))
    _mark_process_dead(tmp_path)

    with pytest.raises(ExtractionError, match='journal identity mismatch'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert final.read_bytes() == b'previous output'
    assert path.is_file()


@pytest.mark.parametrize('name', [JOURNAL_NAME, 'backups/output.parquet'])
def test_staging_names_cannot_replace_recovery_authority(
    tmp_path: Path, name: str
) -> None:
    """Caller-provided artifact names cannot overwrite recovery internals."""
    publisher = TransactionalPublisher(tmp_path, owner='test')
    publication = publisher.begin()
    before = (publication.staging_dir / JOURNAL_NAME).read_bytes()
    try:
        with pytest.raises(ExtractionError, match='Unsafe staged artifact'):
            publication.stage_path(name)
        assert (publication.staging_dir / JOURNAL_NAME).read_bytes() == before
    finally:
        publication.abort()


@pytest.mark.parametrize('existing_output', [False, True])
@pytest.mark.parametrize('replacement_completed', [False, True])
@pytest.mark.parametrize(
    'caller_write', ['atomic', 'in_place', 'preserve_timestamps']
)
def test_recovery_preserves_caller_output_written_after_interruption(
    tmp_path: Path,
    existing_output: bool,
    replacement_completed: bool,
    caller_write: str,
) -> None:
    """A valid journal cannot claim files written after the transaction."""
    publisher, publication, final = _registered_publication(tmp_path)
    if not existing_output:
        final.unlink()
    publication.mark_validated()
    publication._prepare_backups()
    publication.manifest.phase = 'PUBLISHING'
    publication.manifest.artifacts[0].publishing = True
    publisher._write_manifest(publication.manifest, publication.manifest_path)
    if replacement_completed:
        publisher.operations.replace(
            publication.manifest.artifacts[0].staged_path, final
        )
    expected_caller_bytes = b'caller output after interruption'
    if caller_write == 'preserve_timestamps' and final.exists():
        previous_stat = final.stat()
        expected_caller_bytes = b'X' * previous_stat.st_size
        final.write_bytes(expected_caller_bytes)
        os.utime(
            final,
            ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns),
        )
    elif caller_write == 'atomic':
        new_file = tmp_path / 'caller-new-output.tmp'
        new_file.write_bytes(b'caller output after interruption')
        new_file.replace(final)
    else:
        final.write_bytes(b'caller output after interruption')
    _mark_process_dead(tmp_path)

    with pytest.raises(ExtractionError, match='preserves an output changed'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert final.read_bytes() == expected_caller_bytes
    assert (publication.staging_dir / JOURNAL_NAME).is_file()
    assert (tmp_path / LOCK_NAME / 'owner.json').is_file()


@pytest.mark.parametrize('existing_output', [False, True])
def test_recovery_before_rename_preserves_unchanged_original_output(
    tmp_path: Path, existing_output: bool
) -> None:
    """The durable publishing flag alone does not require output removal."""
    publisher, publication, final = _registered_publication(tmp_path)
    if not existing_output:
        final.unlink()
    publication.mark_validated()
    publication._prepare_backups()
    publication.manifest.phase = 'PUBLISHING'
    publication.manifest.artifacts[0].publishing = True
    publisher._write_manifest(publication.manifest, publication.manifest_path)
    _mark_process_dead(tmp_path)

    recovered = TransactionalPublisher(tmp_path, owner='test').begin()
    recovered.abort()

    if existing_output:
        assert final.read_bytes() == b'previous output'
        assert list(tmp_path.iterdir()) == [final]
    else:
        assert not final.exists()
        assert list(tmp_path.iterdir()) == []


def test_cleanup_preserves_substituted_private_caller_directory(
    tmp_path: Path,
) -> None:
    """An entry swapped after validation is never recursively deleted."""
    caller = tmp_path / 'caller-data'
    caller.mkdir(mode=0o700)
    (caller / 'keep.txt').write_bytes(b'caller-owned contents')

    class SubstituteCleanupRoot(FileOperations):
        """Swap the directory at the actual filesystem cleanup boundary."""

        def rmtree(
            self, path: Path, *, expected_identity: tuple[int, int]
        ) -> None:
            """Expose any deletion through the now-substituted pathname."""
            path.rename(path.with_name(f'{path.name}-moved'))
            caller.rename(path)
            super().rmtree(path, expected_identity=expected_identity)

    publication = TransactionalPublisher(
        tmp_path, owner='test', operations=SubstituteCleanupRoot()
    ).begin()

    with pytest.raises(ExtractionError, match='directory identity changed'):
        publication.abort()

    assert (publication.staging_dir / 'keep.txt').read_bytes() == (
        b'caller-owned contents'
    )


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd, reason='Descriptor-relative cleanup'
)
def test_cleanup_uses_opened_root_after_directory_name_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renaming an opened root never redirects cleanup into a caller tree."""
    caller = tmp_path / 'caller-data'
    caller.mkdir(mode=0o700)
    (caller / 'keep.txt').write_bytes(b'caller-owned contents')
    publication = TransactionalPublisher(tmp_path, owner='test').begin()
    scandir = cleanup.os.scandir
    substituted = False

    def substitute_opened_root(descriptor):
        nonlocal substituted
        if not substituted:
            substituted = True
            publication.staging_dir.rename(
                publication.staging_dir.with_name('moved-private-staging')
            )
            caller.rename(publication.staging_dir)
        return scandir(descriptor)

    monkeypatch.setattr(cleanup.os, 'scandir', substitute_opened_root)

    with pytest.raises(ExtractionError, match='directory identity changed'):
        publication.abort()

    assert substituted is True
    assert (publication.staging_dir / 'keep.txt').read_bytes() == (
        b'caller-owned contents'
    )


def test_recovery_refuses_backup_bytes_changed_with_preserved_timestamps(
    tmp_path: Path,
) -> None:
    """A metadata-identical corrupted backup cannot replace valid output."""
    publisher, publication, final = _registered_publication(tmp_path)
    publication.mark_validated()
    publication._prepare_backups()
    publication.manifest.phase = 'PUBLISHING'
    artifact = publication.manifest.artifacts[0]
    artifact.publishing = True
    publisher._write_manifest(publication.manifest, publication.manifest_path)
    publisher.operations.replace(artifact.staged_path, final)
    backup = artifact.backup_path
    assert backup is not None
    before = backup.stat()
    backup.write_bytes(b'X' * before.st_size)
    os.utime(backup, ns=(before.st_atime_ns, before.st_mtime_ns))
    _mark_process_dead(tmp_path)

    with pytest.raises(ExtractionError, match='backup identity changed'):
        TransactionalPublisher(tmp_path, owner='test').begin()

    assert final.read_bytes() == b'new output'
    assert backup.read_bytes() == b'X' * before.st_size
    assert (publication.staging_dir / JOURNAL_NAME).is_file()
