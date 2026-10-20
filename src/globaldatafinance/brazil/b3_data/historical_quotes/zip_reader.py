"""Bounded byte-preserving reader for B3 COTAHIST ZIP and TXT sources."""

from __future__ import annotations

import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .async_execution import check_phase_cancellation
from .errors import CotahistCatalogError
from .input_validation import (
    _raise_public_input_error,
    open_resolved_cotahist_zip,
    validate_cotahist_input,
)
from .integrity import (
    B3RawLine,
    B3RecordContext,
    CotahistLineTooLongError,
    iter_bounded_cotahist_lines,
)


class ZipFileReaderB3:
    """Open one COTAHIST input and retain exact line bytes and coordinates."""

    def __init__(self, *, limits: ArchiveSafetyLimits | None = None) -> None:
        """Initialize the reader with one immutable safety-policy snapshot."""
        if limits is None:
            limits = ArchiveSafetyLimits.from_environment()
        self._limits = limits

    @property
    def limits(self) -> ArchiveSafetyLimits:
        """Return the archive safety limits used by this reader."""
        return self._limits

    def iter_raw_lines(
        self,
        source_path: str,
        *,
        expected_member: str | None = None,
    ) -> Iterator[B3RawLine]:
        """Yield bounded records before decoding, preserving physical bytes."""
        path = Path(source_path)
        try:
            with self._open_source(
                path, expected_member=expected_member
            ) as source:
                yield from source.iter_raw_lines()
        except CotahistCatalogError as error:
            _raise_public_input_error(path, error)

    @contextmanager
    def _open_source(
        self, path: Path, *, expected_member: str | None = None
    ) -> Iterator[_OpenedCotahistSource]:
        """Own one validated container through bounded hash and scan passes."""
        check_phase_cancellation()
        if path.suffix.casefold() == '.txt':
            member = validate_cotahist_input(path, limits=self._limits)
            _check_expected_member(path, member or '', expected_member)
            with path.open('rb') as stream:
                yield _OpenedCotahistSource(path, '', self._limits, txt=stream)
            return
        with open_resolved_cotahist_zip(path, limits=self._limits) as (
            archive,
            member,
        ):
            _check_expected_member(path, member, expected_member)
            yield _OpenedCotahistSource(path, member, self._limits, archive)

    def iter_lines(
        self, source_path: str
    ) -> Iterator[tuple[str, B3RecordContext]]:
        """Decode byte-preserved records for string-based callers."""
        for raw_line in self.iter_raw_lines(source_path):
            yield raw_line.content.decode('latin-1'), raw_line.context

    async def read_lines_from_zip(self, zip_path: str) -> AsyncIterator[str]:
        """Retain the asynchronous reader contract without per-line pauses."""
        for line, _context in self.iter_lines(zip_path):
            yield line


@dataclass
class _OpenedCotahistSource:
    """Provide repeatable bounded passes only on an owned validated handle."""

    path: Path
    member: str
    limits: ArchiveSafetyLimits
    archive: zipfile.ZipFile | None = None
    txt: BinaryIO | None = None

    @contextmanager
    def _open_stream(self) -> Iterator[BinaryIO]:
        """Reopen the validated ZIP member or rewind the owned TXT stream."""
        if self.txt is not None:
            self.txt.seek(0)
            yield self.txt
            return
        if self.archive is None:
            raise RuntimeError('COTAHIST source has no owned container')
        try:
            with open_limited_zip_member(
                self.archive,
                self.member,
                archive_path=self.path,
                limits=self.limits,
            ) as source:
                yield source
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(str(self.path), str(error)) from error

    def iter_raw_lines(self) -> Iterator[B3RawLine]:
        """Build record contexts during a strict document or worker scan."""
        with self._open_stream() as source:
            try:
                for line_number, raw_line in iter_bounded_cotahist_lines(
                    source
                ):
                    yield _raw_line_with_context(
                        raw_line, self.path.name, self.member, line_number
                    )
            except CotahistLineTooLongError as error:
                detail = (
                    f'{self.member}: {error}' if self.member else str(error)
                )
                raise ExtractionError(str(self.path), detail) from error

    def iter_chunks(self) -> Iterator[bytes]:
        """Hash exact uncompressed bytes without per-line materialization."""
        with self._open_stream() as source:
            while True:
                check_phase_cancellation()
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                yield chunk


def _check_expected_member(
    path: Path, member: str, expected_member: str | None
) -> None:
    """Reject member replacement before yielding any quotation bytes."""
    if expected_member is not None and member != expected_member:
        raise ExtractionError(
            str(path),
            'COTAHIST ZIP member changed since catalog resolution: '
            f'expected {expected_member!r}, observed {member!r}',
        )


def _raw_line_with_context(
    raw_line: bytes,
    source_basename: str,
    member: str,
    line_number: int,
) -> B3RawLine:
    """Split one terminator without changing the fixed-width record bytes."""
    content, terminator = _split_line_terminator(raw_line)
    context = B3RecordContext(
        source_basename=source_basename,
        zip_member=member,
        physical_line=line_number,
        logical_record=line_number,
        record_type=content[:2].decode('latin-1'),
        raw_preview=content[:80].decode('latin-1'),
    )
    return B3RawLine(content, terminator, context)


def _split_line_terminator(raw_line: bytes) -> tuple[bytes, bytes]:
    """Split one physical CRLF, LF, or CR line ending."""
    if raw_line.endswith(b'\r\n'):
        return raw_line[:-2], b'\r\n'
    if raw_line.endswith(b'\n') or raw_line.endswith(b'\r'):
        return raw_line[:-1], raw_line[-1:]
    return raw_line, b''
