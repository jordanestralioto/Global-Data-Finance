"""Provide generic ZIP and text extraction primitives."""

from __future__ import annotations

import asyncio
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO

from ..core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
    validate_zip_archive,
)
from ..macro_exceptions import CorruptedZipError, ExtractionError


class ExtractorAdapter:
    """Archive utilities shared by source-owned extraction pipelines."""

    CHUNK_SIZE_TXT = 8192

    @staticmethod
    def list_files_in_zip(
        zip_path: str,
        extension: str,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> list[str]:
        """List validated archive members whose names end with an extension."""
        path = Path(zip_path)
        if not path.exists():
            raise FileNotFoundError(f'ZIP file not found: {zip_path}')
        try:
            with zipfile.ZipFile(zip_path, 'r') as archive:
                infos = validate_zip_archive(
                    path, archive, limits=archive_limits
                )
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(zip_path, str(error)) from error
        return [
            info.filename
            for info in infos
            if not info.is_dir()
            and info.filename.lower().endswith(extension.lower())
        ]

    @staticmethod
    def open_file_from_zip(
        zip_file: zipfile.ZipFile,
        filename: str,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> IO[bytes]:
        """Open one bounded validated archive member for streaming."""
        archive_path = zip_file.filename or 'unknown.zip'
        if zip_file.filename is not None:
            validate_zip_archive(archive_path, zip_file, limits=archive_limits)
        if filename not in zip_file.namelist():
            raise ExtractionError(
                archive_path, f'File not found in ZIP: {filename!r}'
            )
        return open_limited_zip_member(
            zip_file,
            filename,
            archive_path=archive_path,
            limits=archive_limits,
        )

    async def extract_txt_from_zip_async(
        self,
        zip_path: str,
        member_name: str | None = None,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> AsyncIterator[str]:
        """Yield Latin-1 archive text lines without extracting them to disk."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as archive:
                infos = validate_zip_archive(
                    zip_path, archive, limits=archive_limits
                )
                selected = member_name or self._first_txt_member(infos)
                if selected is None:
                    raise ExtractionError(
                        zip_path, 'No .TXT file found in ZIP'
                    )
                with self.open_file_from_zip(
                    archive, selected, archive_limits=archive_limits
                ) as source:
                    for number, raw_line in enumerate(source, start=1):
                        yield raw_line.decode('latin-1').rstrip('\r\n')
                        if number % self.CHUNK_SIZE_TXT == 0:
                            await asyncio.sleep(0)
        except zipfile.BadZipFile as error:
            raise CorruptedZipError(zip_path, str(error)) from error
        except (CorruptedZipError, ExtractionError, FileNotFoundError):
            raise
        except OSError as error:
            raise ExtractionError(
                zip_path, f'Error reading TXT from ZIP: {error}'
            ) from error

    @staticmethod
    def _first_txt_member(
        infos: list[zipfile.ZipInfo],
    ) -> str | None:
        """Choose the first archive-order TXT member when none is supplied."""
        return next(
            (
                info.filename
                for info in infos
                if not info.is_dir() and info.filename.lower().endswith('.txt')
            ),
            None,
        )
