"""Reopenable CVM source handling and strict encoding normalization."""

from __future__ import annotations

import codecs
import hashlib
import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO

from .....core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
    validate_zip_archive,
)
from .....macro_exceptions import DiskFullError, ExtractionError
from .constants import CP1252_DEFINED_RANGE, CP1252_UNDEFINED
from .models import EncodingPlan

_CP1252_TRANSLATION = bytes(
    2 if byte in CP1252_UNDEFINED else 1 if byte in CP1252_DEFINED_RANGE else 0
    for byte in range(256)
)
_CP1252_RELEVANT_BYTES = CP1252_DEFINED_RANGE | CP1252_UNDEFINED
_CP1252_DELETE_BYTES = bytes(
    byte for byte in range(256) if byte not in _CP1252_RELEVANT_BYTES
)


class ReopenableCsvSource:
    """Open a validated ZIP member afresh for every CVM pipeline pass."""

    def __init__(
        self,
        source_path: str | Path,
        member_name: str,
        *,
        limits: ArchiveSafetyLimits | None = None,
    ) -> None:
        """Store the source ZIP path and its already-selected CSV member."""
        self.source_path = Path(source_path)
        self.member_name = member_name
        self.limits = limits

    @contextmanager
    def open_binary(self) -> Iterator[BinaryIO]:
        """Yield a new bounded member stream without retaining ZIP state."""
        try:
            with zipfile.ZipFile(self.source_path, 'r') as archive:
                validate_zip_archive(
                    self.source_path, archive, limits=self.limits
                )
                with open_limited_zip_member(
                    archive,
                    self.member_name,
                    archive_path=self.source_path,
                    limits=self.limits,
                ) as member:
                    yield member
        except zipfile.BadZipFile as error:
            raise ExtractionError(
                str(self.source_path), f'Could not reopen ZIP member: {error}'
            ) from error


def detect_encoding(source: ReopenableCsvSource) -> EncodingPlan:
    """Select the documented UTF-8, CP1252, or Latin-1 policy."""
    (
        utf8_valid,
        has_bom,
        has_cp1252_defined_byte,
        has_cp1252_undefined_byte,
    ) = _scan_encoding(source)
    if has_bom and not utf8_valid:
        raise ExtractionError(
            str(source.source_path),
            'UTF-8 BOM is present but the complete CSV member is invalid',
        )
    if utf8_valid:
        return EncodingPlan(
            encoding='utf-8',
            has_utf8_bom=has_bom,
            needs_utf8_spool=False,
            source_member=source.member_name,
        )
    return EncodingPlan(
        encoding=_fallback_encoding(
            has_cp1252_defined_byte,
            has_cp1252_undefined_byte,
        ),
        has_utf8_bom=False,
        needs_utf8_spool=True,
        source_member=source.member_name,
    )


def prepare_utf8_source(
    source: ReopenableCsvSource,
    plan: EncodingPlan,
    staging_dir: Path,
) -> Path | None:
    """Spool strict non-UTF-8 input as a transaction-private UTF-8 file."""
    if not plan.needs_utf8_spool:
        return None
    digest = hashlib.sha256(
        f'{source.source_path}:{plan.source_member}'.encode()
    ).hexdigest()[:16]
    spool = staging_dir / f'.cvm-{digest}.utf8.csv'
    try:
        decoder = codecs.getincrementaldecoder(plan.encoding)(errors='strict')
        with source.open_binary() as raw, spool.open('wb') as target:
            while chunk := raw.read(64 * 1024):
                decoded = decoder.decode(chunk, final=False)
                target.write(decoded.encode('utf-8'))
            target.write(decoder.decode(b'', final=True).encode('utf-8'))
    except OSError as error:
        if getattr(error, 'errno', None) == 28:
            raise DiskFullError(str(spool)) from error
        raise ExtractionError(
            str(source.source_path),
            f'Could not create UTF-8 staging spool: {error}',
        ) from error
    return spool


@contextmanager
def text_source(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
) -> Iterator[TextIO]:
    """Yield a strict text reader with the selected decoding plan."""
    if utf8_source is not None:
        with utf8_source.open(encoding='utf-8', newline='') as opened:
            yield opened
        return
    with source.open_binary() as raw:
        _consume_utf8_bom(source, raw, plan)
        with io.TextIOWrapper(raw, encoding='utf-8', newline='') as text:
            yield text


@contextmanager
def binary_source(
    source: ReopenableCsvSource,
    utf8_source: Path | None,
    plan: EncodingPlan,
) -> Iterator[BinaryIO]:
    """Yield UTF-8 bytes for Arrow without invoking text conversion."""
    if utf8_source is not None:
        with utf8_source.open('rb') as opened:
            yield opened
        return
    with source.open_binary() as raw:
        _consume_utf8_bom(source, raw, plan)
        yield raw


def _scan_encoding(
    source: ReopenableCsvSource,
) -> tuple[bool, bool, bool, bool]:
    """Validate UTF-8 incrementally while collecting fallback evidence."""
    utf8_valid = True
    has_cp1252_defined_byte = False
    has_cp1252_undefined_byte = False
    decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
    prefix = bytearray()
    try:
        with source.open_binary() as opened:
            while chunk := opened.read(64 * 1024):
                if len(prefix) < len(codecs.BOM_UTF8):
                    prefix.extend(chunk[: len(codecs.BOM_UTF8) - len(prefix)])
                cp1252_markers = chunk.translate(
                    _CP1252_TRANSLATION,
                    _CP1252_DELETE_BYTES,
                )
                has_cp1252_defined_byte |= b'\x01' in cp1252_markers
                has_cp1252_undefined_byte |= b'\x02' in cp1252_markers
                if utf8_valid:
                    try:
                        decoder.decode(chunk, final=False)
                    except UnicodeDecodeError:
                        utf8_valid = False
            if utf8_valid:
                decoder.decode(b'', final=True)
    except UnicodeDecodeError:
        utf8_valid = False
    return (
        utf8_valid,
        bytes(prefix) == codecs.BOM_UTF8,
        has_cp1252_defined_byte,
        has_cp1252_undefined_byte,
    )


def _fallback_encoding(
    has_cp1252_defined_byte: bool,
    has_cp1252_undefined_byte: bool,
) -> str:
    """Choose the lossless non-UTF-8 encoding from observed bytes."""
    if has_cp1252_undefined_byte:
        return 'latin-1'
    if has_cp1252_defined_byte:
        return 'cp1252'
    return 'latin-1'


def _consume_utf8_bom(
    source: ReopenableCsvSource,
    raw: BinaryIO,
    plan: EncodingPlan,
) -> None:
    """Remove exactly one validated UTF-8 BOM before a later pass."""
    if not plan.has_utf8_bom:
        return
    prefix = raw.read(len(codecs.BOM_UTF8))
    if prefix != codecs.BOM_UTF8:
        raise ExtractionError(
            str(source.source_path),
            'UTF-8 BOM disappeared while reopening CSV member',
        )
