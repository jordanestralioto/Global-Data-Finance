"""Artifact staging, commit, rollback, and cleanup for one transaction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...macro_exceptions import ExtractionError
from .paths import require_strict_descendant
from .types import ArtifactIntent, PublicationManifest

if TYPE_CHECKING:
    from .publisher import TransactionalPublisher


class TransactionalPublication:
    """Collect validated artifacts and publish them as a recoverable batch."""

    def __init__(
        self,
        publisher: TransactionalPublisher,
        manifest: PublicationManifest,
        manifest_path: Path,
    ) -> None:
        """Store the exclusive publication state created by the publisher."""
        self._publisher = publisher
        self.manifest = manifest
        self.manifest_path = manifest_path
        self._finished = False

    @property
    def staging_dir(self) -> Path:
        """Return the private staging directory for source-owned artifacts."""
        return self.manifest.staging_dir

    def stage_path(self, name: str) -> Path:
        """Return a safe source-owned path inside transaction staging."""
        relative = Path(name)
        if (
            not name
            or relative.is_absolute()
            or '..' in relative.parts
            or relative == Path()
        ):
            raise ExtractionError(
                str(self._publisher.destination_dir),
                f'Unsafe staged artifact name: {name!r}',
            )
        path = (self.staging_dir / relative).resolve()
        self._publisher._require_descendant(path, self.staging_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def add_artifact(
        self,
        *,
        final_path: Path,
        staged_path: Path,
        expected_rows: int,
        schema_fingerprint: str,
    ) -> None:
        """Register one already-written and source-validated staged output."""
        if self.manifest.phase != 'OPEN':
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Artifacts can only be added while publication is OPEN',
            )
        final = final_path.resolve()
        staged = staged_path.resolve()
        require_strict_descendant(final, self._publisher.destination_dir)
        require_strict_descendant(staged, self.staging_dir)
        if (
            isinstance(expected_rows, bool)
            or not isinstance(expected_rows, int)
            or expected_rows < 0
        ):
            raise ExtractionError(
                str(final),
                'Expected artifact row count must be a non-negative integer',
            )
        if not isinstance(schema_fingerprint, str) or not schema_fingerprint:
            raise ExtractionError(
                str(final), 'Artifact schema fingerprint cannot be empty'
            )
        if any(item.final_path == final for item in self.manifest.artifacts):
            raise ExtractionError(str(final), 'Duplicate final artifact path')
        self.manifest.artifacts.append(
            ArtifactIntent(
                final_path=final,
                staged_path=staged,
                expected_rows=expected_rows,
                schema_fingerprint=schema_fingerprint,
            )
        )
        self._publisher._write_manifest(self.manifest, self.manifest_path)

    def mark_validated(self) -> None:
        """Record that every source-specific staged validation passed."""
        if not self.manifest.artifacts:
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Publication requires at least one staged artifact',
            )
        missing = [
            str(item.staged_path)
            for item in self.manifest.artifacts
            if not item.staged_path.is_file()
        ]
        if missing:
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Staged artifact is missing: ' + ', '.join(missing),
            )
        self._publisher.ensure_backup_space(self.manifest.artifacts)
        self.manifest.phase = 'VALIDATED'
        self._publisher._write_manifest(self.manifest, self.manifest_path)

    def commit(self) -> None:
        """Publish all validated artifacts or restore all previous outputs."""
        if self.manifest.phase != 'VALIDATED':
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Publication must be VALIDATED before commit',
            )
        committed_durable = False
        try:
            self._prepare_backups()
            self.manifest.phase = 'BACKUPS_READY'
            self._publisher._write_manifest(self.manifest, self.manifest_path)
            self.manifest.phase = 'PUBLISHING'
            self._publisher._write_manifest(self.manifest, self.manifest_path)
            self._publish_artifacts()
            self.manifest.phase = 'COMMITTED'
            self._publisher._write_manifest(self.manifest, self.manifest_path)
            committed_durable = True
            self._cleanup_committed()
            self._finished = True
        except Exception as error:
            if committed_durable:
                raise ExtractionError(
                    str(self._publisher.destination_dir),
                    'Publication committed but cleanup is pending at '
                    f'{self.manifest_path}: {error}',
                ) from error
            self._rollback_after_failure(error)

    def abort(self) -> None:
        """Discard only unpublished transaction state after source failure."""
        if self._finished:
            return
        if self.manifest.phase in {'COMMITTED', 'CLEANUP_PENDING'}:
            self._cleanup_committed()
            self._finished = True
            return
        if self.manifest.phase in {
            'BACKUPS_READY',
            'PUBLISHING',
            'ROLLING_BACK',
        }:
            self._rollback_after_failure(
                ExtractionError(
                    str(self._publisher.destination_dir),
                    'Publication aborted before commit completed',
                )
            )
            return
        self.manifest.phase = 'ROLLED_BACK'
        self._publisher._write_manifest(self.manifest, self.manifest_path)
        self._cleanup_rolled_back()
        self._finished = True

    def _prepare_backups(self) -> None:
        backup_dir = self.staging_dir / 'backups'
        existing = [
            item
            for item in self._ordered_artifacts()
            if item.final_path.exists()
        ]
        if not existing:
            return
        self._publisher.operations.mkdir(backup_dir)
        for index, item in enumerate(existing):
            backup = backup_dir / f'{index:04d}-{item.final_path.name}'
            try:
                self._publisher.operations.link(item.final_path, backup)
                self._publisher._sync_directory(backup_dir)
            except OSError:
                self._publisher.operations.copy2(item.final_path, backup)
                self._publisher._sync_file(backup)
                self._publisher._sync_directory(backup_dir)
            item.existed_before = True
            item.backup_path = backup
            self._publisher._write_manifest(self.manifest, self.manifest_path)

    def _publish_artifacts(self) -> None:
        for item in self._ordered_artifacts():
            item.publishing = True
            self._publisher._write_manifest(self.manifest, self.manifest_path)
            self._publisher.operations.replace(
                item.staged_path, item.final_path
            )
            self._publisher._sync_directory(self._publisher.destination_dir)
            item.publishing = False
            item.published = True
            self._publisher._write_manifest(self.manifest, self.manifest_path)

    def _rollback_after_failure(self, original_error: Exception) -> None:
        self.manifest.phase = 'ROLLING_BACK'
        self._publisher._write_manifest(self.manifest, self.manifest_path)
        errors = self._restore_published_artifacts()
        if errors:
            detail = '; '.join(errors)
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Publication failed and recovery is preserved at '
                f'{self.manifest_path}: {type(original_error).__name__}: '
                f'{original_error}; rollback failures: {detail}',
            ) from original_error
        self.manifest.phase = 'ROLLED_BACK'
        self._publisher._write_manifest(self.manifest, self.manifest_path)
        try:
            self._cleanup_rolled_back()
        except (ExtractionError, OSError) as cleanup_error:
            raise ExtractionError(
                str(self._publisher.destination_dir),
                'Publication rollback completed but cleanup is pending at '
                f'{self.manifest_path}: {cleanup_error}',
            ) from original_error
        self._finished = True
        raise ExtractionError(
            str(self._publisher.destination_dir),
            'Publication failed and all modified outputs were restored: '
            f'{type(original_error).__name__}: {original_error}',
        ) from original_error

    def _restore_published_artifacts(self) -> list[str]:
        errors: list[str] = []
        for item in reversed(self._ordered_artifacts()):
            if not (item.published or item.publishing):
                continue
            try:
                if item.backup_path is not None:
                    if not item.backup_path.exists():
                        raise FileNotFoundError(
                            f'Backup is missing: {item.backup_path}'
                        )
                    self._publisher.operations.replace(
                        item.backup_path, item.final_path
                    )
                elif item.final_path.exists():
                    self._publisher.operations.unlink(item.final_path)
                self._publisher._sync_directory(
                    self._publisher.destination_dir
                )
                item.publishing = False
                item.published = False
                self._publisher._write_manifest(
                    self.manifest, self.manifest_path
                )
            except OSError as error:
                errors.append(
                    f'{item.final_path}: {type(error).__name__}: {error}'
                )
        return errors

    def _cleanup_committed(self) -> None:
        self.manifest.phase = 'CLEANUP_PENDING'
        self._publisher._write_manifest(self.manifest, self.manifest_path)
        self._cleanup_derived_state()

    def _cleanup_rolled_back(self) -> None:
        self._cleanup_derived_state()

    def _cleanup_derived_state(self) -> None:
        self._publisher._remove_tree(self.staging_dir)
        self._publisher._remove_file(self.manifest_path)
        self._publisher._release_lock_for(self.manifest.transaction_id)

    def _ordered_artifacts(self) -> list[ArtifactIntent]:
        return sorted(
            self.manifest.artifacts,
            key=lambda item: item.final_path.as_posix().casefold(),
        )
