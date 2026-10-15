"""Durable manifest serialization and safe recovery-record parsing."""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ...macro_exceptions import ExtractionError
from .durability import sync_directory, sync_file
from .ownership import (
    directory_identity,
    read_private_json,
    require_private_entry,
)
from .paths import (
    bind_artifact_destination,
    relative_to,
    require_descendant,
    require_strict_descendant,
)
from .types import (
    JOURNAL_NAME,
    LOCK_NAME,
    MANIFEST_PREFIX,
    PHASES,
    ArtifactIntent,
    FileOperations,
    PublicationManifest,
)


class ManifestStore:
    """Persist and read manifests without knowing source-specific schemas."""

    def __init__(
        self,
        destination_dir: Path,
        source_path: str,
        operations: FileOperations,
    ) -> None:
        """Bind storage to one validated destination filesystem."""
        self.destination_dir = destination_dir
        self.source_path = source_path
        self.operations = operations

    def write(self, manifest: PublicationManifest, path: Path) -> None:
        """Atomically serialize one allowed manifest state."""
        if manifest.phase not in PHASES:
            raise ExtractionError(
                self.source_path,
                f'Unsupported transaction manifest state: {manifest.phase}',
            )
        self._validate_paths(manifest)
        self._validate_identity(manifest, path)
        payload = self._payload(manifest)
        payload['destination_identity'] = directory_identity(
            self.destination_dir
        )
        payload['staging_identity'] = directory_identity(manifest.staging_dir)
        self.write_json_atomically(
            manifest.staging_dir / JOURNAL_NAME, payload
        )
        self.write_json_atomically(
            path, payload, temporary_dir=manifest.staging_dir
        )

    def read(self, path: Path) -> PublicationManifest:
        """Read and validate one manifest before recovery touches artifacts."""
        payload = read_private_json(path)
        discovered = self._from_payload(
            {
                **payload,
                'phase': 'OPEN',
                'artifacts': [],
                'source_descriptors': [],
            }
        )
        self._validate_identity(discovered, path)
        authoritative = self.read_journal(discovered.staging_dir)
        if (
            discovered.transaction_id != authoritative.transaction_id
            or discovered.owner != authoritative.owner
        ):
            raise ExtractionError(
                self.source_path, 'Transaction discovery identity mismatch'
            )
        return authoritative

    def read_journal(self, staging_dir: Path) -> PublicationManifest:
        """Use only a private journal as authority for destructive recovery."""
        require_private_entry(staging_dir, directory=True)
        payload = read_private_json(staging_dir / JOURNAL_NAME)
        manifest = self._from_payload(payload)
        self._validate_identity(
            manifest,
            self.destination_dir
            / f'{MANIFEST_PREFIX}{manifest.transaction_id}.json',
        )
        if (
            manifest.staging_dir != staging_dir
            or payload.get('destination_identity')
            != directory_identity(self.destination_dir)
            or payload.get('staging_identity')
            != directory_identity(staging_dir)
        ):
            raise ExtractionError(
                self.source_path, 'Private recovery journal identity mismatch'
            )
        return manifest

    def _from_payload(self, payload: dict[str, object]) -> PublicationManifest:
        try:
            version = payload.get('version')
            if isinstance(version, bool) or not isinstance(version, int):
                raise ValueError('version must be an integer')
            manifest = PublicationManifest(
                transaction_id=str(payload['transaction_id']),
                owner=str(payload['owner']),
                destination_dir=self.destination_dir,
                staging_dir=self._path_from_payload(payload, 'staging_dir'),
                created_at=str(payload['created_at']),
                artifacts=self._artifacts(payload),
                source_descriptors=self._source_descriptors(payload),
                phase=str(payload['phase']),
                version=version,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ExtractionError(
                self.source_path,
                f'Transaction manifest has invalid fields: {error}',
            ) from error
        self._validate_paths(manifest)
        return manifest

    def _validate_identity(
        self, manifest: PublicationManifest, path: Path
    ) -> None:
        if (
            manifest.version != 2
            or re.fullmatch(r'[0-9a-f]{32}', manifest.transaction_id) is None
            or path.parent != self.destination_dir
            or path.name != f'{MANIFEST_PREFIX}{manifest.transaction_id}.json'
            or manifest.staging_dir.parent
            not in {self.destination_dir, self.destination_dir / LOCK_NAME}
            or not manifest.staging_dir.name.startswith(
                f'{MANIFEST_PREFIX}{manifest.transaction_id}-'
            )
            or manifest.phase not in PHASES
        ):
            raise ExtractionError(
                self.source_path, 'Unverifiable transaction recovery identity'
            )
        if manifest.staging_dir.parent != self.destination_dir:
            require_private_entry(manifest.staging_dir.parent, directory=True)
        require_private_entry(manifest.staging_dir, directory=True)

    def _artifacts(self, payload: dict[str, object]) -> list[ArtifactIntent]:
        entries = payload['artifacts']
        if not isinstance(entries, list):
            raise ValueError('artifacts must be an array')
        artifacts: list[ArtifactIntent] = []
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError('artifact must be an object')
            expected_rows = item.get('expected_rows')
            if (
                isinstance(expected_rows, bool)
                or not isinstance(expected_rows, int)
                or expected_rows < 0
            ):
                raise ValueError(
                    'artifact expected_rows must be a non-negative integer'
                )
            fingerprint = item.get('schema_fingerprint')
            if not isinstance(fingerprint, str) or not fingerprint:
                raise ValueError(
                    'artifact schema_fingerprint must be a non-empty string'
                )
            artifacts.append(
                ArtifactIntent(
                    final_path=self._artifact_path(item, 'final_path'),
                    staged_path=self._artifact_path(item, 'staged_path'),
                    expected_rows=expected_rows,
                    schema_fingerprint=fingerprint,
                    backup_path=(
                        self._artifact_path(item, 'backup_path')
                        if item.get('backup_path')
                        else None
                    ),
                    existed_before=self._flag(item, 'existed_before'),
                    publishing=self._flag(item, 'publishing'),
                    published=self._flag(item, 'published'),
                    publication_identity=self._identity(
                        item, 'publication_identity'
                    ),
                    original_identity=self._identity(
                        item, 'original_identity'
                    ),
                    backup_identity=self._identity(item, 'backup_identity'),
                    publication_sha256=self._digest(
                        item, 'publication_sha256'
                    ),
                    original_sha256=self._digest(item, 'original_sha256'),
                    backup_sha256=self._digest(item, 'backup_sha256'),
                )
            )
        return artifacts

    @staticmethod
    def _flag(entry: dict[str, object], key: str) -> bool:
        value = entry.get(key, False)
        if not isinstance(value, bool):
            raise ValueError(f'artifact {key} must be a boolean')
        return value

    @staticmethod
    def _identity(entry: dict[str, object], key: str) -> list[int] | None:
        value = entry.get(key)
        if value is None:
            return None
        if (
            not isinstance(value, list)
            or len(value) != 4
            or any(
                isinstance(part, bool) or not isinstance(part, int)
                for part in value
            )
        ):
            raise ValueError(f'artifact {key} must contain four integers')
        return value

    @staticmethod
    def _digest(entry: dict[str, object], key: str) -> str | None:
        value = entry.get(key)
        if value is not None and (
            not isinstance(value, str)
            or re.fullmatch(r'[0-9a-f]{64}', value) is None
        ):
            raise ValueError(f'artifact {key} must be a SHA256 digest')
        return value

    @staticmethod
    def _source_descriptors(
        payload: dict[str, object],
    ) -> list[dict[str, str]]:
        """Validate the bounded, human-readable source descriptors."""
        entries = payload.get('source_descriptors', [])
        if not isinstance(entries, list):
            raise ValueError('source_descriptors must be an array')
        descriptors: list[dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in entry.items()
            ):
                raise ValueError(
                    'source_descriptors must contain string mappings'
                )
            descriptors.append(dict(entry))
        return descriptors

    def _payload(self, manifest: PublicationManifest) -> dict[str, object]:
        return {
            'version': manifest.version,
            'transaction_id': manifest.transaction_id,
            'owner': manifest.owner,
            'destination_dir': '.',
            'staging_dir': relative_to(
                manifest.staging_dir, self.destination_dir
            ),
            'phase': manifest.phase,
            'created_at': manifest.created_at,
            'source_descriptors': manifest.source_descriptors,
            'artifacts': [
                {
                    **asdict(item),
                    'final_path': relative_to(
                        item.final_path, self.destination_dir
                    ),
                    'staged_path': relative_to(
                        item.staged_path, self.destination_dir
                    ),
                    'backup_path': (
                        relative_to(item.backup_path, self.destination_dir)
                        if item.backup_path is not None
                        else None
                    ),
                }
                for item in manifest.artifacts
            ],
        }

    def _path_from_payload(self, payload: dict[str, object], key: str) -> Path:
        value = payload.get(key)
        if not isinstance(value, str):
            raise ValueError(f'{key} must be a relative path string')
        if Path(value).is_absolute() or '..' in Path(value).parts:
            raise ValueError(f'{key} must stay relative to the destination')
        path = self.destination_dir / value
        if key == 'final_path':
            return bind_artifact_destination(path, self.destination_dir)
        if path.is_symlink():
            raise ValueError(f'{key} cannot be a symbolic link')
        path = path.resolve()
        require_descendant(path, self.destination_dir)
        return path

    def _artifact_path(self, payload: object, key: str) -> Path:
        if not isinstance(payload, dict):
            raise ValueError('artifact must be an object')
        return self._path_from_payload(payload, key)

    def _validate_paths(self, manifest: PublicationManifest) -> None:
        require_strict_descendant(manifest.staging_dir, self.destination_dir)
        for item in manifest.artifacts:
            bind_artifact_destination(item.final_path, self.destination_dir)
            require_strict_descendant(item.staged_path, manifest.staging_dir)
            if item.staged_path.relative_to(manifest.staging_dir).parts[0] in {
                JOURNAL_NAME,
                'backups',
            }:
                raise ExtractionError(
                    self.source_path, 'Staged artifact uses recovery state'
                )
            if item.existed_before != (item.backup_path is not None):
                raise ExtractionError(
                    self.source_path,
                    'Artifact backup ownership is inconsistent',
                )
            if (item.publishing or item.published) and (
                item.publication_identity is None
                or item.publication_sha256 is None
                or (
                    item.existed_before
                    and (
                        item.original_identity is None
                        or item.backup_identity is None
                        or item.original_sha256 is None
                        or item.backup_sha256 is None
                    )
                )
            ):
                raise ExtractionError(
                    self.source_path, 'Recovery artifact identity is missing'
                )
            if item.backup_path is not None:
                require_strict_descendant(
                    item.backup_path, manifest.staging_dir / 'backups'
                )
            if manifest.phase in {
                'OPEN',
                'VALIDATED',
                'BACKUPS_READY',
                'ROLLED_BACK',
            } and (item.publishing or item.published):
                raise ExtractionError(
                    self.source_path,
                    'Artifact publication phase is inconsistent',
                )

    def write_json_atomically(
        self,
        path: Path,
        payload: dict[str, object],
        *,
        temporary_dir: Path | None = None,
    ) -> None:
        """Persist an internal lock or manifest with durable replacement."""
        require_descendant(path.resolve(), self.destination_dir)
        temporary = (temporary_dir or path.parent) / (
            f'{path.name}-{uuid4().hex}.tmp'
        )
        require_descendant(temporary.resolve(), self.destination_dir)
        encoded = (json.dumps(payload, sort_keys=True) + '\n').encode('utf-8')
        try:
            self.operations.write_bytes(temporary, encoded)
            sync_file(self.operations, temporary)
            self.operations.replace(temporary, path)
            sync_directory(self.operations, path.parent)
        finally:
            if temporary.exists():
                with contextlib.suppress(OSError):
                    self.operations.unlink(temporary)
