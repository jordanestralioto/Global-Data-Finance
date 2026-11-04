"""Read and validate annual COTAHIST source files with bounded I/O."""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from scripts.cotahist_oracle.errors import OracleMismatch
from scripts.cotahist_oracle.row_digest import new_rows_digest
from scripts.file_digests import sha256_file

_FILE_PATTERN = re.compile(r'^COTAHIST_A(?P<year>[0-9]{4})\.(ZIP|TXT)$', re.I)

_MEMBER_PATTERNS = (
    re.compile(r'^COTAHIST_A(?P<year>[0-9]{4})\.TXT$', re.I),
    re.compile(r'^COTAHIST_A(?P<year>[0-9]{4})$', re.I),
    re.compile(r'^COTAHIST\.A(?P<year>[0-9]{4})$', re.I),
)


@dataclass
class SourceFacts:
    """Capture independently inspected facts about an annual source file."""

    path: Path
    year: int
    member: str
    outer_sha256: str
    content_sha256: str
    uncompressed_bytes: int
    header: bytes | None = None
    trailer: bytes | None = None
    declared_count: int | None = None
    quote_count: int = 0
    blank_lines: int = 0
    trailer_convention: str = ''
    generation_date: date | None = None
    first_date: date | None = None
    last_date: date | None = None
    market_counts: dict[str, int] = field(default_factory=dict)
    unknown_market_counts: dict[str, int] = field(default_factory=dict)
    rows_digest: Any = field(default_factory=new_rows_digest)


def inspect_source(path: Path) -> SourceFacts:
    """Inspect a COTAHIST file and collect independently validated facts."""
    match = _FILE_PATTERN.fullmatch(path.name)
    if match is None or not path.is_file():
        raise OracleMismatch(f'invalid COTAHIST input path: {path}')
    year = int(match.group('year'))
    member = _resolve_member(path, year)
    digest = hashlib.sha256()
    size = 0
    with _open_source(path, member) as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return SourceFacts(
        path=path,
        year=year,
        member=member,
        outer_sha256=sha256_file(path),
        content_sha256=digest.hexdigest(),
        uncompressed_bytes=size,
    )


def _resolve_member(path: Path, year: int) -> str:
    if path.suffix.casefold() == '.txt':
        return ''
    try:
        with zipfile.ZipFile(path, 'r') as archive:
            candidates = []
            for info in archive.infolist():
                if (
                    info.is_dir()
                    or '/' in info.filename
                    or '\\' in info.filename
                ):
                    continue
                if any(
                    (match := pattern.fullmatch(info.filename)) is not None
                    and int(match.group('year')) == year
                    for pattern in _MEMBER_PATTERNS
                ):
                    candidates.append(info.filename)
            if len(candidates) != 1:
                raise OracleMismatch(
                    f'{path.name}: expected one root COTAHIST member, found '
                    f'{len(candidates)}'
                )
            return candidates[0]
    except (OSError, zipfile.BadZipFile) as error:
        raise OracleMismatch(
            f'{path.name}: cannot open ZIP: {error}'
        ) from error


@contextmanager
def _open_source(path: Path, member: str) -> Iterator[Any]:
    if path.suffix.casefold() == '.txt':
        with path.open('rb') as stream:
            yield stream
        return
    with (
        zipfile.ZipFile(path, 'r') as archive,
        archive.open(member, 'r') as stream,
    ):
        yield stream


def iter_bounded_lines(path: Path, member: str) -> Iterator[tuple[int, bytes]]:
    """Yield source lines through the bounded reader."""
    with _open_source(path, member) as stream:
        line_number = 0
        while raw_line := stream.readline(248):
            line_number += 1
            if len(raw_line) > 247:
                raise OracleMismatch(
                    f'{path.name}: physical line {line_number} exceeds '
                    '247 bytes'
                )
            yield line_number, raw_line


def split_line_terminator(raw_line: bytes) -> tuple[bytes, bytes]:
    """Separate a recognized line ending from a raw line."""
    if raw_line.endswith(b'\r\n'):
        return raw_line[:-2], b'\r\n'
    if raw_line.endswith(b'\n') or raw_line.endswith(b'\r'):
        return raw_line[:-1], raw_line[-1:]
    return raw_line, b''


def validate_header(
    record: bytes, source: SourceFacts, line_number: int
) -> date:
    """Validate and return the trading date recorded in a file header."""
    if (
        source.header is not None
        or source.quote_count
        or source.trailer is not None
    ):
        raise OracleMismatch(
            f'{source.path.name}: duplicate or misplaced header at line '
            f'{line_number}'
        )
    if record[2:15] != f'COTAHIST.{source.year:04d}'.encode():
        raise OracleMismatch(f'{source.path.name}: invalid header file id')
    if record[15:23] != b'BOVESPA ':
        raise OracleMismatch(f'{source.path.name}: invalid header origin')
    generation_date = _parse_control_date(record[23:31], source.path.name)
    if record[31:245] != b' ' * 214:
        raise OracleMismatch(f'{source.path.name}: invalid header reserve')
    return generation_date


def validate_trailer(
    record: bytes, source: SourceFacts, line_number: int
) -> None:
    """Validate the totals and date range recorded in a file trailer."""
    if (
        source.header is None
        or source.trailer is not None
        or not source.quote_count
    ):
        raise OracleMismatch(
            f'{source.path.name}: misplaced trailer at line {line_number}'
        )
    if record[2:31] != source.header[2:31]:
        raise OracleMismatch(
            f'{source.path.name}: header/trailer identity differs'
        )
    if record[42:245] != b' ' * 203:
        raise OracleMismatch(f'{source.path.name}: invalid trailer reserve')
    count = record[31:42]
    require_ascii_digits(count, f'{source.path.name}: trailer count')
    source.declared_count = int(count)
    source.trailer = record


def _parse_control_date(raw_value: bytes, source_name: str) -> date:
    require_ascii_digits(raw_value, f'{source_name}: generation date')
    try:
        return date(
            int(raw_value[0:4]), int(raw_value[4:6]), int(raw_value[6:8])
        )
    except ValueError as error:
        raise OracleMismatch(
            f'{source_name}: invalid generation date'
        ) from error


def require_ascii_digits(value: bytes, label: str) -> None:
    """Require a byte field to contain only ASCII digits."""
    if not value or not value.isascii() or not value.isdigit():
        raise OracleMismatch(f'{label} must contain ASCII digits')


def source_sort_key(path: Path) -> tuple[int, str, str]:
    """Return the stable annual COTAHIST file ordering key."""
    match = _FILE_PATTERN.fullmatch(path.name)
    year = int(match.group('year')) if match else 9999
    return year, path.name.casefold(), path.name
