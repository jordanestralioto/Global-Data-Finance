"""Validate one caller-owned COTAHIST filename and container."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .errors import CotahistCatalogError
from .member_resolver import resolve_cotahist_member

COTAHIST_FILENAME_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})\.(?P<extension>ZIP|TXT)$',
    re.IGNORECASE,
)


def validate_cotahist_input(
    path: str | Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str | None:
    """Validate an input filename/container and return a ZIP member name."""
    candidate = Path(path).expanduser().resolve()
    match = COTAHIST_FILENAME_PATTERN.fullmatch(candidate.name)
    if match is None:
        raise CotahistCatalogError(
            'COTAHIST input must use the COTAHIST_AYYYY.ZIP or '
            f'COTAHIST_AYYYY.TXT filename contract: {candidate}'
        )
    if not candidate.is_file():
        raise CotahistCatalogError(
            f'COTAHIST input is not a regular file: {candidate}'
        )
    try:
        if candidate.stat().st_size == 0:
            raise CotahistCatalogError(f'COTAHIST input is empty: {candidate}')
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST input is unreadable: {candidate}'
        ) from error
    if match.group('extension').casefold() == 'txt':
        return None
    return _validate_zip(candidate, limits=limits)


def validate_and_resolve_cotahist_input(
    path: str | Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str | None:
    """Translate filename/container failures to the public exception tree."""
    candidate = Path(path)
    try:
        return validate_cotahist_input(candidate, limits=limits)
    except CotahistCatalogError as error:
        cause = error.__cause__
        if isinstance(cause, CorruptedZipError):
            raise cause from error
        if isinstance(cause, zipfile.BadZipFile):
            raise CorruptedZipError(str(candidate), str(cause)) from error
        raise ExtractionError(str(candidate), str(error)) from error


def _validate_zip(
    path: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str:
    """Validate archive safety and resolve the unique annual member."""
    try:
        with zipfile.ZipFile(path, 'r') as zip_file:
            infos = validate_zip_archive(path, zip_file, limits=limits)
            validate_zip_crc_with_limits(
                path,
                zip_file,
                infos=infos,
                limits=limits,
            )
            member = resolve_cotahist_member(path, infos)
            if zip_file.getinfo(member).file_size == 0:
                raise CotahistCatalogError(
                    f'COTAHIST member is empty: {path}!{member}'
                )
            return member
    except CotahistCatalogError:
        raise
    except (
        CorruptedZipError,
        ExtractionError,
        OSError,
        zipfile.BadZipFile,
    ) as error:
        raise CotahistCatalogError(
            f'Invalid COTAHIST ZIP {path}: {type(error).__name__}: {error}'
        ) from error
