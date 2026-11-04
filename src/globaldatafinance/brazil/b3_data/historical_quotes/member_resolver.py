"""Resolve supported COTAHIST members from validated ZIP metadata."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath

from ....macro_exceptions import ExtractionError

COTAHIST_FILENAME_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})\.(?P<extension>ZIP|TXT)$',
    re.IGNORECASE,
)
_HISTORICAL_UNDERSCORE_MEMBER_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})$', re.IGNORECASE
)
_HISTORICAL_MEMBER_PATTERN = re.compile(
    r'^COTAHIST\.A(?P<year>\d{4})$', re.IGNORECASE
)


def resolve_cotahist_member(
    zip_path: Path, infos: list[zipfile.ZipInfo]
) -> str:
    """Resolve one root-level COTAHIST member from ZIP metadata."""
    external_year = _external_cotahist_year(zip_path)
    candidates, nested_candidates = _member_candidates(infos)
    if nested_candidates:
        names = ', '.join(sorted(nested_candidates, key=str.casefold))
        raise ExtractionError(
            str(zip_path),
            'No valid COTAHIST member at archive root; nested candidates: '
            f'{names}',
        )

    if not candidates:
        raise ExtractionError(
            str(zip_path), 'No valid COTAHIST member found in ZIP archive'
        )
    if len(candidates) != 1:
        names = ', '.join(name for name, _year in candidates)
        raise ExtractionError(
            str(zip_path),
            f'Ambiguous COTAHIST members in ZIP archive: {names}',
        )

    member_name, member_year = candidates[0]
    if member_year != external_year:
        raise ExtractionError(
            str(zip_path),
            'COTAHIST archive year does not match its internal member: '
            f'{external_year} != {member_year}',
        )
    return member_name


def _external_cotahist_year(zip_path: Path) -> str:
    match = COTAHIST_FILENAME_PATTERN.fullmatch(zip_path.name)
    if match is None or match.group('extension').casefold() != 'zip':
        raise ExtractionError(
            str(zip_path),
            'ZIP input must use the COTAHIST_AYYYY.ZIP filename contract',
        )
    return match.group('year')


def _member_year(member_name: str) -> str | None:
    """Return the year from one supported root-level member name."""
    modern = COTAHIST_FILENAME_PATTERN.fullmatch(member_name)
    if modern is not None and modern.group('extension').casefold() == 'txt':
        return modern.group('year')
    for pattern in (
        _HISTORICAL_UNDERSCORE_MEMBER_PATTERN,
        _HISTORICAL_MEMBER_PATTERN,
    ):
        match = pattern.fullmatch(member_name)
        if match is not None:
            return match.group('year')
    return None


def _member_candidates(
    infos: list[zipfile.ZipInfo],
) -> tuple[list[tuple[str, str]], list[str]]:
    candidates: list[tuple[str, str]] = []
    nested_candidates: list[str] = []
    for info in infos:
        if info.is_dir():
            continue
        normalized_name = info.filename.replace('\\', '/')
        basename = PurePosixPath(normalized_name).name
        basename_year = _member_year(basename)
        if basename_year is None:
            continue
        if normalized_name != basename:
            nested_candidates.append(info.filename)
            continue
        member_year = _member_year(info.filename)
        if member_year is not None:
            candidates.append((info.filename, member_year))
    return candidates, nested_candidates
