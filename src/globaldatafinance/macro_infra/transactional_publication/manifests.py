"""Durable manifest serialization and safe recovery-record parsing."""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict
from pathlib import Path

from ...macro_exceptions import ExtractionError
from .durability import sync_directory, sync_file
from .paths import relative_to, require_descendant, require_strict_descendant
from .types import PHASES, ArtifactIntent, FileOperations, PublicationManifest


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
        self.write_json_atomically(path, self._payload(manifest))

    def read(self, path: Path) -> PublicationManifest:
        """Read and validate one manifest before recovery touches artifacts."""
        require_descendant(path.resolve(), self.destination_dir)
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise ExtractionError(
                self.source_path,
                f'Cannot read transaction manifest {path}: {error}',
            ) from error
        if not isinstance(payload, dict):
            raise ExtractionError(
                self.source_path, 'Transaction manifest is malformed'
            )
        try:
            manifest = PublicationManifest(
                transaction_id=str(payload['transaction_id']),
                owner=str(payload['owner']),
                destination_dir=self.destination_dir,
                staging_dir=self._path_from_payload(payload, 'staging_dir'),
                created_at=str(payload['created_at']),
                artifacts=self._artifacts(payload),
                source_descriptors=self._source_descriptors(payload),
                phase=str(payload['phase']),
                version=int(payload.get('version', 1)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ExtractionError(
                self.source_path,
                f'Transaction manifest has invalid fields: {error}',
            ) from error
        self._validate_paths(manifest)
        return manifest

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
                    existed_before=bool(item.get('existed_before', False)),
                    publishing=bool(item.get('publishing', False)),
                    published=bool(item.get('published', False)),
                )
            )
        return artifacts

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
        path = (self.destination_dir / value).resolve()
        require_descendant(path, self.destination_dir)
        return path

    def _artifact_path(self, payload: object, key: str) -> Path:
        if not isinstance(payload, dict):
            raise ValueError('artifact must be an object')
        return self._path_from_payload(payload, key)

    def _validate_paths(self, manifest: PublicationManifest) -> None:
        require_strict_descendant(manifest.staging_dir, self.destination_dir)
        for item in manifest.artifacts:
            require_strict_descendant(item.final_path, self.destination_dir)
            require_strict_descendant(item.staged_path, manifest.staging_dir)
            if item.backup_path is not None:
                require_strict_descendant(
                    item.backup_path, manifest.staging_dir
                )

    def write_json_atomically(
        self, path: Path, payload: dict[str, object]
    ) -> None:
        """Persist an internal lock or manifest with durable replacement."""
        require_descendant(path.resolve(), self.destination_dir)
        temporary = path.with_name(f'{path.name}.tmp')
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
