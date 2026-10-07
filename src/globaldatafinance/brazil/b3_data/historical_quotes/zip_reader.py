"""Bounded byte-preserving reader for B3 COTAHIST ZIP and TXT sources."""

from __future__ import annotations

import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .input_validation import (
    open_resolved_cotahist_zip,
    validate_and_resolve_cotahist_input,
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
        if path.suffix.casefold() == '.txt':
            member = self._validate_cotahist_input(path)
            _check_expected_member(path, member or '', expected_member)
            yield from self._iter_txt(path)
            return
        with open_resolved_cotahist_zip(path, limits=self._limits) as (
            archive,
            member,
        ):
            _check_expected_member(path, member, expected_member)
            yield from self._iter_zip(path, member, archive)

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

    def _validate_cotahist_input(self, path: Path) -> str | None:
        return validate_and_resolve_cotahist_input(path, limits=self._limits)

    def _iter_txt(self, path: Path) -> Iterator[B3RawLine]:
        with path.open('rb') as source:
            try:
                for line_number, raw_line in iter_bounded_cotahist_lines(
                    source
                ):
                    yield _raw_line_with_context(
                        raw_line, path.name, '', line_number
                    )
            except CotahistLineTooLongError as error:
                raise ExtractionError(str(path), str(error)) from error

    def _iter_zip(
        self, path: Path, member: str, archive: zipfile.ZipFile
    ) -> Iterator[B3RawLine]:
        try:
            with open_limited_zip_member(
                archive,
                member,
                archive_path=path,
                limits=self._limits,
            ) as source:
                try:
                    for line_number, raw_line in iter_bounded_cotahist_lines(
                        source
                    ):
                        yield _raw_line_with_context(
                            raw_line, path.name, member, line_number
                        )
                except CotahistLineTooLongError as error:
                    raise ExtractionError(
                        str(path), f'{member}: {error}'
                    ) from error
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(str(path), str(error)) from error


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
