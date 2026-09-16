"""Shared limits and structural validation for untrusted ZIP archives.

The policy deliberately validates central-directory metadata before a caller
asks :mod:`zipfile` to verify CRCs or decompresses a member. Metadata checks
bound normal archives; a counting reader bounds the bytes actually delivered
by a decompressor when metadata is corrupt or deceptive.
"""

from __future__ import annotations

import io
import stat
import zipfile
from collections.abc import Buffer
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from ..macro_exceptions import CorruptedZipError
from .archive_names import canonicalize_archive_member_name
from .config import ArchiveSafetySettings


@dataclass(frozen=True)
class ArchiveSafetyLimits:
    """Validated resource limits applied to one ZIP archive."""

    max_archive_bytes: int
    max_members: int
    max_member_uncompressed_bytes: int
    max_total_uncompressed_bytes: int
    max_compression_ratio: float

    @classmethod
    def from_settings(
        cls, configured: ArchiveSafetySettings
    ) -> ArchiveSafetyLimits:
        """Build an immutable policy from validated archive settings."""
        return cls(
            max_archive_bytes=configured.max_archive_bytes,
            max_members=configured.max_members,
            max_member_uncompressed_bytes=(
                configured.max_member_uncompressed_bytes
            ),
            max_total_uncompressed_bytes=(
                configured.max_total_uncompressed_bytes
            ),
            max_compression_ratio=configured.max_compression_ratio,
        )

    @classmethod
    def from_environment(cls) -> ArchiveSafetyLimits:
        """Build a fresh immutable policy from the current environment."""
        return cls.from_settings(ArchiveSafetySettings())


def validate_zip_archive(
    archive_path: str | Path,
    zip_file: zipfile.ZipFile,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> list[zipfile.ZipInfo]:
    """Validate ZIP metadata before CRC verification or decompression.

    Args:
        archive_path: Filesystem path of the source archive.
        zip_file: Already-open archive whose central directory is inspected.
        limits: Injected policy for tests or a caller-specific bounded use.

    Returns:
        The validated central-directory entries in archive order.

    Raises:
        CorruptedZipError: If the archive exceeds a limit or contains an
            unsafe member name, type, encryption flag, duplicate output, or
            file/descendant collision.
    """
    source_path = Path(archive_path)
    if limits is None:
        limits = ArchiveSafetyLimits.from_environment()
    _validate_archive_size(source_path, limits)

    infos = zip_file.infolist()
    if len(infos) > limits.max_members:
        _raise_rejected_archive(
            source_path,
            'member count exceeds configured limit '
            f'({len(infos)} > {limits.max_members})',
        )

    total_uncompressed_size = 0
    normalized_infos: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        normalized_name = _validate_member_metadata(source_path, info, limits)
        if normalized_name in normalized_infos:
            _raise_rejected_archive(
                source_path,
                'contains duplicate output member names after '
                f'case-insensitive normalization: {info.filename!r}',
            )
        normalized_infos[normalized_name] = info

        if info.is_dir():
            continue

        total_uncompressed_size += info.file_size
        if total_uncompressed_size > limits.max_total_uncompressed_bytes:
            _raise_rejected_archive(
                source_path,
                'total uncompressed size exceeds configured limit '
                f'({total_uncompressed_size} > '
                f'{limits.max_total_uncompressed_bytes})',
            )

    _reject_file_ancestor_collisions(source_path, normalized_infos)
    return infos


def open_limited_zip_member(
    zip_file: zipfile.ZipFile,
    member_name: str,
    *,
    archive_path: str | Path | None = None,
    limits: ArchiveSafetyLimits | None = None,
    byte_budget: ArchiveByteBudget | None = None,
) -> io.BufferedReader:
    """Open one ZIP member with a real-byte counter around its stream.

    The archive should be validated with :func:`validate_zip_archive` before
    this function is called. This extra boundary is intentional: it detects a
    decompressor delivering more bytes than the central-directory metadata
    advertised, without loading the member in memory.
    """
    if limits is None:
        limits = ArchiveSafetyLimits.from_environment()
    source_path = Path(archive_path or zip_file.filename or 'unknown.zip')
    try:
        info = zip_file.getinfo(member_name)
    except KeyError as error:
        raise CorruptedZipError(
            str(source_path), f'ZIP member does not exist: {member_name!r}'
        ) from error

    _validate_member_metadata(source_path, info, limits)
    budget = byte_budget or ArchiveByteBudget(
        max_total_bytes=limits.max_total_uncompressed_bytes
    )
    raw_member = zip_file.open(info, 'r')
    return io.BufferedReader(
        _LimitedZipMemberStream(
            raw_member,
            archive_path=source_path,
            member_name=member_name,
            max_member_bytes=limits.max_member_uncompressed_bytes,
            byte_budget=budget,
        )
    )


def validate_zip_crc_with_limits(
    archive_path: str | Path,
    zip_file: zipfile.ZipFile,
    *,
    limits: ArchiveSafetyLimits | None = None,
    infos: list[zipfile.ZipInfo] | None = None,
) -> None:
    """Verify member CRCs through bounded streams after metadata validation.

    ``ZipFile.testzip()`` reads unbounded streams itself. This equivalent
    verification preserves the required CRC check while keeping the actual
    decompressed-byte counter at the archive boundary.
    """
    source_path = Path(archive_path)
    if limits is None:
        limits = ArchiveSafetyLimits.from_environment()
    validated_infos = (
        infos
        if infos is not None
        else validate_zip_archive(source_path, zip_file, limits=limits)
    )
    budget = ArchiveByteBudget(
        max_total_bytes=limits.max_total_uncompressed_bytes
    )
    try:
        for info in validated_infos:
            if info.is_dir():
                continue
            with open_limited_zip_member(
                zip_file,
                info.filename,
                archive_path=source_path,
                limits=limits,
                byte_budget=budget,
            ) as member:
                while member.read(64 * 1024):
                    pass
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise CorruptedZipError(
            str(source_path), f'CRC validation failed: {error}'
        ) from error


@dataclass
class ArchiveByteBudget:
    """Track decompressed bytes across one caller-defined streaming phase."""

    max_total_bytes: int
    consumed_bytes: int = 0

    def consume(
        self, count: int, archive_path: Path, member_name: str
    ) -> None:
        """Record bytes and reject a stream phase exceeding the total cap."""
        self.consumed_bytes += count
        if self.consumed_bytes > self.max_total_bytes:
            _raise_rejected_archive(
                archive_path,
                'actual decompressed bytes exceed configured total limit '
                f'while reading {member_name!r} '
                f'({self.consumed_bytes} > {self.max_total_bytes})',
            )


class _LimitedZipMemberStream(io.RawIOBase):
    """Raw stream wrapper that counts data after ZIP decompression."""

    def __init__(
        self,
        raw_member: IO[bytes],
        *,
        archive_path: Path,
        member_name: str,
        max_member_bytes: int,
        byte_budget: ArchiveByteBudget,
    ) -> None:
        self._raw_member = raw_member
        self._archive_path = archive_path
        self._member_name = member_name
        self._max_member_bytes = max_member_bytes
        self._byte_budget = byte_budget
        self._consumed_bytes = 0

    def readable(self) -> bool:
        """Expose the binary reader capability required by BufferedReader."""
        return True

    def readinto(self, buffer: Buffer) -> int:
        """Read at most one byte past a configured cap before rejecting it."""
        if self.closed:
            raise ValueError('I/O operation on closed ZIP member stream')

        target_buffer = memoryview(buffer)
        remaining_with_probe = (
            self._max_member_bytes + 1 - self._consumed_bytes
        )
        if remaining_with_probe <= 0:
            _raise_rejected_archive(
                self._archive_path,
                'actual decompressed bytes exceed configured member limit '
                f'while reading {self._member_name!r}',
            )
        requested_size = min(target_buffer.nbytes, remaining_with_probe)
        data = self._raw_member.read(requested_size)
        size = len(data)
        if size == 0:
            return 0

        self._consumed_bytes += size
        self._byte_budget.consume(size, self._archive_path, self._member_name)
        if self._consumed_bytes > self._max_member_bytes:
            _raise_rejected_archive(
                self._archive_path,
                'actual decompressed bytes exceed configured member limit '
                f'while reading {self._member_name!r} '
                f'({self._consumed_bytes} > {self._max_member_bytes})',
            )

        target_buffer[:size] = data
        return size

    def close(self) -> None:
        """Close the wrapped ZIP stream exactly once."""
        if not self.closed:
            self._raw_member.close()
        super().close()


def _validate_archive_size(
    archive_path: Path, limits: ArchiveSafetyLimits
) -> None:
    try:
        archive_size = archive_path.stat().st_size
    except OSError as error:
        raise CorruptedZipError(
            str(archive_path), f'could not inspect archive size: {error}'
        ) from error
    if archive_size > limits.max_archive_bytes:
        _raise_rejected_archive(
            archive_path,
            'compressed archive size exceeds configured limit '
            f'({archive_size} > {limits.max_archive_bytes})',
        )


def _validate_member_metadata(
    archive_path: Path,
    info: zipfile.ZipInfo,
    limits: ArchiveSafetyLimits,
) -> str:
    """Validate one central-directory entry and return its canonical name."""
    normalized_name = _normalize_member_name(archive_path, info.filename)
    if info.flag_bits & 0x1:
        _raise_rejected_archive(
            archive_path,
            f'encrypted member is not supported: {info.filename!r}',
        )
    _validate_member_type(archive_path, info)

    if info.is_dir():
        return normalized_name
    if info.file_size > limits.max_member_uncompressed_bytes:
        _raise_rejected_archive(
            archive_path,
            'member uncompressed size exceeds configured limit '
            f'for {info.filename!r} ({info.file_size} > '
            f'{limits.max_member_uncompressed_bytes})',
        )
    ratio = info.file_size / max(info.compress_size, 1)
    if ratio > limits.max_compression_ratio:
        _raise_rejected_archive(
            archive_path,
            'member compression ratio exceeds configured limit '
            f'for {info.filename!r} ({ratio:.2f} > '
            f'{limits.max_compression_ratio:.2f})',
        )
    return normalized_name


def _normalize_member_name(archive_path: Path, member_name: str) -> str:
    """Reject path-like ZIP members that could escape a consumer's target."""
    return canonicalize_archive_member_name(archive_path, member_name)


def _reject_file_ancestor_collisions(
    archive_path: Path, normalized_infos: dict[str, zipfile.ZipInfo]
) -> None:
    """Reject a file member that is also an ancestor of another member."""
    for member_name, info in normalized_infos.items():
        if info.is_dir():
            continue
        components = member_name.split('/')
        for component_count in range(1, len(components)):
            ancestor = '/'.join(components[:component_count])
            ancestor_info = normalized_infos.get(ancestor)
            if ancestor_info is not None and not ancestor_info.is_dir():
                _raise_rejected_archive(
                    archive_path,
                    'file ZIP member is an ancestor of another member: '
                    f'{ancestor!r} -> {member_name!r}',
                )


def _validate_member_type(archive_path: Path, info: zipfile.ZipInfo) -> None:
    """Reject symbolic links and non-regular ZIP entries."""
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        _raise_rejected_archive(
            archive_path,
            f'symlink ZIP member is not supported: {info.filename!r}',
        )
    if file_type and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
        _raise_rejected_archive(
            archive_path,
            f'special ZIP member type is not supported: {info.filename!r}',
        )


def _raise_rejected_archive(archive_path: Path, reason: str) -> None:
    """Raise the public archive-rejection exception from one source."""
    raise CorruptedZipError(str(archive_path), reason)
