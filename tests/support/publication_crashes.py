"""Run real process exits at publication filesystem boundaries."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path

from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
    TransactionalPublisher,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    JOURNAL_NAME,
    LOCK_NAME,
    MANIFEST_PREFIX,
)

CRASH_EXIT = 81
ARTIFACT_NAMES = ('first.parquet', 'second.parquet')


class CrashOperations(FileOperations):
    """Exit after real mutations, bypassing exception cleanup and finally."""

    def __init__(self, checkpoint: str, control: Path) -> None:
        """Select one crash or pause point for the worker process."""
        self.checkpoint = checkpoint
        self.control = control
        self.published = 0

    def _reach(self, checkpoint: str) -> None:
        if checkpoint == self.checkpoint:
            os._exit(CRASH_EXIT)

    def _pause(self, checkpoint: str) -> None:
        if checkpoint != self.checkpoint:
            return
        (self.control / 'ready').write_text(str(os.getpid()))
        deadline = time.monotonic() + 20
        while not (self.control / 'release').exists():
            if time.monotonic() > deadline:
                raise TimeoutError(f'{checkpoint} timed out')
            time.sleep(0.01)

    def mkdir(self, path: Path) -> None:
        """Crash or pause before the first ownership record exists."""
        super().mkdir(path)
        if path.name == LOCK_NAME:
            self._reach('lock_created')
            self._pause('pause_initialization')

    def mkdtemp(self, prefix: str, destination: Path) -> Path:
        """Crash before a new private staging directory has a journal."""
        path = super().mkdtemp(prefix, destination)
        self._reach('staging_created')
        return path

    def write_bytes(self, path: Path, payload: bytes) -> None:
        """Crash with complete temporary bytes but before atomic promotion."""
        super().write_bytes(path, payload)
        if path.name.startswith('owner.json-'):
            self._reach('owner_temporary_written')
        elif path.name.startswith(JOURNAL_NAME + '-'):
            self._reach('journal_temporary_written')
        elif path.name.startswith(MANIFEST_PREFIX):
            self._reach('manifest_temporary_written')

    def fsync_file(self, path: Path) -> None:
        """Crash after syncing the initial temporary ownership record."""
        super().fsync_file(path)
        if path.name.startswith('owner.json-'):
            self._reach('owner_temporary_synced')

    def replace(self, source: Path, destination: Path) -> None:
        """Crash around durable journal states and output replacements."""
        super().replace(source, destination)
        if destination.name == 'owner.json':
            self._reach('owner_published')
            self._pause('pause_owned')
        elif destination.name in ARTIFACT_NAMES:
            if source.parent.name == 'backups':
                self._reach('recovery_output_restored')
                self._pause('pause_recovery')
            else:
                self.published += 1
                self._reach(f'output_{self.published}_published')
                if self.published == 1:
                    self._pause('pause_publishing')
        elif destination.name == JOURNAL_NAME:
            phase = json.loads(destination.read_text())['phase']
            self._reach('journal_published')
            self._reach(f'journal_{phase.lower()}')
        elif destination.name.startswith(MANIFEST_PREFIX):
            phase = json.loads(destination.read_text())['phase']
            self._reach('manifest_published')
            self._reach(f'manifest_{phase.lower()}')

    def rmtree(
        self, path: Path, *, expected_identity: tuple[int, int]
    ) -> None:
        """Crash after removing a recovery staging tree or lock directory."""
        super().rmtree(path, expected_identity=expected_identity)
        if path.name == LOCK_NAME:
            self._reach('recovery_lock_removed')
        else:
            self._reach('recovery_staging_removed')


def run_worker(
    destination: Path,
    checkpoint: str,
    action: str,
    *,
    operations: FileOperations | None = None,
    payloads: Mapping[str, bytes] | None = None,
) -> None:
    """Run a real transaction or recovery in an isolated child process."""
    publisher = TransactionalPublisher(
        destination,
        owner='crash-test',
        operations=operations
        or CrashOperations(checkpoint, destination.parent / 'control'),
    )
    publication = publisher.begin()
    if action == 'commit':
        for name in ARTIFACT_NAMES:
            staged = publication.stage_path(name)
            contents = (
                payloads[name]
                if payloads is not None
                else b'new:' + name.encode()
            )
            publisher.operations.write_bytes(staged, contents)
            publication.add_artifact(
                final_path=destination / name,
                staged_path=staged,
                expected_rows=1,
                schema_fingerprint='crash-test-v1',
            )
        publication.mark_validated()
        publication.commit()
    else:
        publication.abort()


if __name__ == '__main__':
    run_worker(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
