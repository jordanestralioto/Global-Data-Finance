"""Validate one caller-owned COTAHIST filename and container."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Never

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .async_execution import check_phase_cancellation
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
    candidate = _validate_input_path(path)
    if candidate.suffix.casefold() == '.txt':
        return None
    return _validate_zip(candidate, limits=limits)


def _validate_input_path(path: str | Path) -> Path:
    """Validate the annual filename and nonempty regular input before I/O."""
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
    return candidate


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
        _raise_public_input_error(candidate, error)


@contextmanager
def open_resolved_cotahist_zip(
    path: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> Iterator[tuple[zipfile.ZipFile, str]]:
    """Keep the fully validated archive open for bounded member reading."""
    try:
        with _open_validated_zip(path, limits=limits) as validated:
            yield validated
    except CotahistCatalogError as error:
        _raise_public_input_error(path, error)


def _raise_public_input_error(
    path: Path, error: CotahistCatalogError
) -> Never:
    """Preserve container causes in the public B3 exception hierarchy."""
    cause = error.__cause__
    if isinstance(cause, CorruptedZipError):
        raise cause from error
    if isinstance(cause, zipfile.BadZipFile):
        raise CorruptedZipError(str(path), str(cause)) from error
    raise ExtractionError(str(path), str(error)) from error


def _validate_zip(
    path: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str:
    """Validate archive safety and resolve the unique annual member."""
    with _open_validated_zip(path, limits=limits) as (_archive, member):
        return member


@contextmanager
def _open_validated_zip(
    path: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> Iterator[tuple[zipfile.ZipFile, str]]:
    """Validate every member once on the archive handle used by the reader."""
    candidate = _validate_input_path(path)
    archive: zipfile.ZipFile | None = None
    try:
        archive = zipfile.ZipFile(candidate, 'r')
        infos = validate_zip_archive(candidate, archive, limits=limits)
        validate_zip_crc_with_limits(
            candidate,
            archive,
            infos=infos,
            limits=limits,
            cancellation_check=check_phase_cancellation,
        )
        member = resolve_cotahist_member(candidate, infos)
        if archive.getinfo(member).file_size == 0:
            raise CotahistCatalogError(
                f'COTAHIST member is empty: {candidate}!{member}'
            )
    except BaseException as error:
        if archive is not None:
            archive.close()
        if isinstance(
            error,
            (CorruptedZipError, ExtractionError, OSError, zipfile.BadZipFile),
        ):
            raise CotahistCatalogError(
                f'Invalid COTAHIST ZIP {candidate}: '
                f'{type(error).__name__}: {error}'
            ) from error
        raise
    try:
        yield archive, member
    finally:
        archive.close()
