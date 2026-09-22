"""Synchronous, contextual COTAHIST source reader for B3 workers."""

from __future__ import annotations

import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .catalog import CotahistCatalogError, validate_cotahist_input
from .integrity import B3RecordContext


class ZipFileReaderB3:
    """Open validated COTAHIST ZIP or TXT sources one line at a time."""

    def __init__(self, *, limits: ArchiveSafetyLimits | None = None) -> None:
        """Initialize the reader with one immutable safety-policy snapshot."""
        if limits is None:
            limits = ArchiveSafetyLimits.from_environment()
        self._limits = limits

    @property
    def limits(self) -> ArchiveSafetyLimits:
        """Return the archive safety limits used by this reader."""
        return self._limits

    def iter_lines(
        self, source_path: str
    ) -> Iterator[tuple[str, B3RecordContext]]:
        """Yield decoded lines and exact source coordinates synchronously."""
        path = Path(source_path)
        member = self._validate_cotahist_input(path)
        if path.suffix.casefold() == '.txt':
            yield from self._iter_txt(path)
            return
        if member is None:
            raise ExtractionError(str(path), 'COTAHIST ZIP member is missing')
        yield from self._iter_zip(path, member)

    async def read_lines_from_zip(self, zip_path: str) -> AsyncIterator[str]:
        """Retain the asynchronous reader contract without per-line pauses."""
        for line, _context in self.iter_lines(zip_path):
            yield line

    def _validate_cotahist_input(self, path: Path) -> str | None:
        try:
            return validate_cotahist_input(path, limits=self._limits)
        except CotahistCatalogError as error:
            cause = error.__cause__
            if isinstance(cause, CorruptedZipError):
                raise cause from error
            if isinstance(cause, zipfile.BadZipFile):
                raise CorruptedZipError(str(path), str(cause)) from error
            raise ExtractionError(str(path), str(error)) from error

    def _iter_txt(self, path: Path) -> Iterator[tuple[str, B3RecordContext]]:
        with path.open('rb') as source:
            for line_number, raw_line in enumerate(source, start=1):
                yield self._line_with_context(
                    raw_line, path.name, path.name, line_number
                )

    def _iter_zip(
        self, path: Path, member: str
    ) -> Iterator[tuple[str, B3RecordContext]]:
        try:
            with zipfile.ZipFile(path, 'r') as archive:
                infos = validate_zip_archive(
                    path, archive, limits=self._limits
                )
                validate_zip_crc_with_limits(
                    path, archive, infos=infos, limits=self._limits
                )
                with open_limited_zip_member(
                    archive,
                    member,
                    archive_path=path,
                    limits=self._limits,
                ) as source:
                    for line_number, raw_line in enumerate(source, start=1):
                        yield self._line_with_context(
                            raw_line, path.name, member, line_number
                        )
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(str(path), str(error)) from error

    @staticmethod
    def _line_with_context(
        raw_line: bytes,
        source_basename: str,
        member: str,
        line_number: int,
    ) -> tuple[str, B3RecordContext]:
        line = raw_line.decode('latin-1').rstrip('\r\n')
        return (
            line,
            B3RecordContext(
                source_basename=source_basename,
                zip_member=member,
                physical_line=line_number,
                logical_record=line_number,
                record_type=line[:2],
                raw_preview=line[:80],
            ),
        )
