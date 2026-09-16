"""Validate caller-owned COTAHIST catalogs before real processing."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from pathlib import Path

from ....core.archive_safety import (
    ArchiveSafetyLimits,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .member_resolver import resolve_cotahist_member

_COTAHIST_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})\.(?P<extension>ZIP|TXT)$',
    re.IGNORECASE,
)


class CotahistCatalogError(ValueError):
    """Indicate that a caller-owned COTAHIST catalog is not usable."""


def validate_cotahist_catalog(
    directory: str | Path,
    *,
    expected_years: Iterable[int] | None = None,
    limits: ArchiveSafetyLimits | None = None,
) -> dict[int, list[Path]]:
    """Validate and index official COTAHIST inputs by external year.

    ZIP metadata and CRCs are checked before a catalog is accepted. When
    ``expected_years`` is provided, the catalog must contain exactly that set
    of official years; otherwise every discovered official year is returned.
    A ZIP takes precedence over a TXT input for the same year, but both
    candidates must be individually valid.
    """
    catalog_path = _validate_directory(directory)
    expected = None if expected_years is None else set(expected_years)
    candidates_by_year = _collect_candidates(catalog_path, limits=limits)
    _validate_expected_years(candidates_by_year, expected, catalog_path)
    _validate_conflicts(candidates_by_year, catalog_path)
    return {
        year: sorted(paths, key=lambda path: (path.name.casefold(), path.name))
        for year, paths in sorted(candidates_by_year.items())
    }


def select_cotahist_file(
    files_by_year: dict[int, list[Path]], year: int
) -> Path:
    """Select the ZIP-first input for one already-validated year."""
    try:
        candidates = files_by_year[year]
    except KeyError as error:
        available = ', '.join(str(item) for item in sorted(files_by_year))
        raise CotahistCatalogError(
            f'No COTAHIST input found for year {year}; available: {available}'
        ) from error
    return sorted(
        candidates,
        key=lambda path: (
            path.suffix.casefold() != '.zip',
            path.name.casefold(),
            path.name,
        ),
    )[0]


def validate_cotahist_input(
    path: str | Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str | None:
    """Validate one official COTAHIST input and resolve a ZIP member."""
    candidate = Path(path).expanduser().resolve()
    match = _COTAHIST_PATTERN.fullmatch(candidate.name)
    if match is None:
        raise CotahistCatalogError(
            'COTAHIST input must use the COTAHIST_AYYYY.ZIP or '
            f'COTAHIST_AYYYY.TXT filename contract: {candidate}'
        )
    if not candidate.is_file():
        raise CotahistCatalogError(
            f'COTAHIST input is not a regular file: {candidate}'
        )
    return _validate_candidate(
        candidate,
        match.group('extension').casefold(),
        limits=limits,
    )


def _validate_directory(directory: str | Path) -> Path:
    catalog_path = Path(directory).expanduser().resolve()
    if not catalog_path.exists():
        raise CotahistCatalogError(
            f'COTAHIST directory does not exist: {catalog_path}'
        )
    if not catalog_path.is_dir():
        raise CotahistCatalogError(
            f'COTAHIST path is not a directory: {catalog_path}'
        )
    try:
        children = list(catalog_path.iterdir())
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST directory cannot be inspected: {catalog_path}'
        ) from error
    if not children:
        raise CotahistCatalogError(
            f'COTAHIST directory is empty: {catalog_path}'
        )
    return catalog_path


def _collect_candidates(
    directory: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> dict[int, list[Path]]:
    candidates_by_year: dict[int, list[Path]] = {}
    for candidate in sorted(directory.iterdir(), key=lambda path: path.name):
        if not candidate.is_file():
            continue
        match = _COTAHIST_PATTERN.fullmatch(candidate.name)
        if match is None:
            continue
        year = int(match.group('year'))
        _validate_candidate(
            candidate,
            match.group('extension').casefold(),
            limits=limits,
        )
        candidates_by_year.setdefault(year, []).append(candidate)
    return candidates_by_year


def _validate_candidate(
    path: Path,
    extension: str,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str | None:
    try:
        if path.stat().st_size == 0:
            raise CotahistCatalogError(f'COTAHIST input is empty: {path}')
        with path.open('rb') as handle:
            if handle.read(1) == b'':
                raise CotahistCatalogError(f'COTAHIST input is empty: {path}')
    except CotahistCatalogError:
        raise
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST input is unreadable: {path}'
        ) from error

    if extension == 'zip':
        return _validate_zip(path, limits=limits)
    try:
        with path.open('rb') as lines:
            _require_quote_data_record(lines, path)
    except CotahistCatalogError:
        raise
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST input is unreadable: {path}'
        ) from error
    return None


def _validate_zip(
    path: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> str:
    try:
        with zipfile.ZipFile(path, 'r') as zip_file:
            infos = validate_zip_archive(path, zip_file, limits=limits)
            validate_zip_crc_with_limits(
                path,
                zip_file,
                infos=infos,
                limits=limits,
            )
            member_name = resolve_cotahist_member(path, infos)
            member_info = zip_file.getinfo(member_name)
            if member_info.file_size == 0:
                raise CotahistCatalogError(
                    f'COTAHIST member is empty: {path}!{member_name}'
                )
            with zip_file.open(member_info, 'r') as member:
                _require_quote_data_record(member, path, member_name)
            return member_name
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


def _require_quote_data_record(
    lines: Iterable[bytes],
    path: Path,
    member_name: str | None = None,
) -> None:
    """Require one type-01 quote record before an input can be processed."""
    try:
        has_quote_record = any(line.startswith(b'01') for line in lines)
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST input is unreadable: {path}'
        ) from error
    if has_quote_record:
        return
    input_label = str(path)
    if member_name is not None:
        input_label = f'{input_label}!{member_name}'
    raise CotahistCatalogError(
        f'COTAHIST input has no type-01 quote data record: {input_label}'
    )


def _validate_expected_years(
    candidates_by_year: dict[int, list[Path]],
    expected_years: set[int] | None,
    directory: Path,
) -> None:
    if expected_years is None:
        if not candidates_by_year:
            raise CotahistCatalogError(
                f'No official COTAHIST inputs found in {directory}'
            )
        return
    missing = sorted(expected_years - set(candidates_by_year))
    extra = sorted(set(candidates_by_year) - expected_years)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f'missing years: {missing}')
        if extra:
            details.append(f'unexpected years: {extra}')
        mismatch = '; '.join(details)
        raise CotahistCatalogError(
            f'COTAHIST catalog does not match expected years: {mismatch}'
        )


def _validate_conflicts(
    candidates_by_year: dict[int, list[Path]], directory: Path
) -> None:
    for year, candidates in candidates_by_year.items():
        extensions = [path.suffix.casefold() for path in candidates]
        for extension in ('.zip', '.txt'):
            if extensions.count(extension) > 1:
                names = ', '.join(path.name for path in candidates)
                raise CotahistCatalogError(
                    f'Conflicting COTAHIST inputs for year {year} in '
                    f'{directory}: {names}'
                )
