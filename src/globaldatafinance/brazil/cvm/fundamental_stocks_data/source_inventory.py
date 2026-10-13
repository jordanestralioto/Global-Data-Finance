"""Input identity and exact expected CVM artifact inventory."""

from __future__ import annotations

import hashlib
import re
import zipfile
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from ....core import get_logger
from ....core.archive_safety import ArchiveSafetyLimits, validate_zip_archive
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .download_paths import parquet_basename

logger = get_logger(__name__)


@dataclass(frozen=True)
class SourceInventory:
    """The archive fingerprint and member identity of every expected output."""

    sha256: str
    artifacts: dict[Path, str]


def inspect_source(
    source: Path,
    destination: Path,
    *,
    limits: ArchiveSafetyLimits | None,
    archive: zipfile.ZipFile | None = None,
) -> SourceInventory:
    """Validate names and bind all expected outputs to the consumed ZIP."""
    artifacts: dict[Path, str] = {}
    names: set[str] = set()
    try:
        with (
            nullcontext(archive)
            if archive is not None
            else zipfile.ZipFile(source)
        ) as opened:
            infos = validate_zip_archive(source, opened, limits=limits)
            for info in infos:
                if info.is_dir() or not info.filename.casefold().endswith(
                    '.csv'
                ):
                    continue
                name = parquet_basename(info.filename)
                if name.casefold() in names:
                    raise ExtractionError(str(source), 'CSV basenames collide')
                names.add(name.casefold())
                artifacts[destination / name] = info.filename
            fingerprint = archive_fingerprint(source, opened)
    except zipfile.BadZipFile as error:
        raise CorruptedZipError(str(source), str(error)) from error
    if not artifacts:
        raise ExtractionError(
            str(source), 'Archive does not contain any CSV members'
        )
    return SourceInventory(sha256=fingerprint, artifacts=artifacts)


def archive_fingerprint(source: Path, archive: zipfile.ZipFile) -> str:
    """Hash the exact descriptor used to read ZIP metadata and members."""
    raw = archive.fp
    if raw is None:
        raise ExtractionError(str(source), 'Source archive is closed')
    position = raw.tell()
    try:
        raw.seek(0)
        digest = hashlib.sha256()
        while chunk := raw.read(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        raw.seek(position)


def validate_source_unchanged(
    source: Path, archive: zipfile.ZipFile, expected_sha256: str
) -> None:
    """Reject in-place writes or pathname replacements before publication."""
    with source.open('rb') as current:
        current_sha256 = hashlib.file_digest(current, 'sha256').hexdigest()
    if (
        current_sha256 != expected_sha256
        or archive_fingerprint(source, archive) != expected_sha256
    ):
        raise ExtractionError(
            str(source), 'CVM source changed during extraction'
        )


def validate_output_inventory(
    source: Path, destination: Path, inventory: SourceInventory
) -> None:
    """Reject obsolete outputs from this archive without deleting user data."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    official = re.fullmatch(
        r'(cgvn|dfp|fca|fre|ipe|itr|vlmo)_cia_aberta_(\d{4})\.zip',
        source.name,
        flags=re.IGNORECASE,
    )
    obsolete: list[str] = []
    for candidate in destination.glob('*.parquet'):
        if candidate in inventory.artifacts or not candidate.is_file():
            continue
        if official is not None and (
            candidate.name.casefold().startswith(
                f'{official.group(1).casefold()}_cia_aberta_'
            )
            and candidate.name.casefold().endswith(
                f'_{official.group(2)}.parquet'
            )
        ):
            obsolete.append(candidate.name)
            continue
        if candidate.is_symlink():
            continue
        try:
            with pq.ParquetFile(candidate) as parquet:
                metadata = parquet.schema_arrow.metadata or {}
                if metadata.get(b'cvm.source-archive') == source.name.encode(
                    'utf-8'
                ):
                    obsolete.append(candidate.name)
        except (pa.ArrowException, OSError) as error:
            logger.debug(
                'Unidentified unrelated Parquet ownership for %s: %s',
                candidate,
                error,
            )
    if obsolete:
        raise ExtractionError(
            str(source),
            'Obsolete CVM artifacts require a clean destination: '
            + ', '.join(sorted(obsolete)),
        )
