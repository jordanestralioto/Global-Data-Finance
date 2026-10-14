"""Prove complete archive validation on the handle used for source reading."""

from __future__ import annotations

import struct
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import input_validation
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from globaldatafinance.core.archive_safety import ArchiveSafetyLimits
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    ExtractionError,
)
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.integration


def _corrupt_stored_member(path: Path, member: str) -> None:
    """Flip one payload byte while retaining the original stored-member CRC."""
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
        offset = info.header_offset
    payload = bytearray(path.read_bytes())
    name_length, extra_length = struct.unpack_from('<HH', payload, offset + 26)
    payload[offset + 30 + name_length + extra_length] ^= 1
    path.write_bytes(payload)


def test_reader_validates_all_members_once_per_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRC completion precedes yielding lines and is renewed on every read."""
    path = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('extra.bin', b'extra payload')
    calls = []
    original = input_validation.validate_zip_crc_with_limits

    def validate_all(path, archive, *, infos, limits, cancellation_check):
        calls.append(tuple(info.filename for info in infos))
        return original(
            path,
            archive,
            infos=infos,
            limits=limits,
            cancellation_check=cancellation_check,
        )

    monkeypatch.setattr(
        input_validation, 'validate_zip_crc_with_limits', validate_all
    )
    reader = ZipFileReaderB3()
    for _ in range(2):
        assert len(list(reader.iter_raw_lines(str(path)))) == 3
    assert len(calls) == 2
    assert all(
        set(call) == {'COTAHIST_A2024.TXT', 'extra.bin'} for call in calls
    )


@pytest.mark.parametrize('member', ['COTAHIST_A2024.TXT', 'extra.bin'])
def test_reader_rejects_corrupt_selected_or_unused_member_before_yield(
    tmp_path: Path, member: str
) -> None:
    """Every member CRC is checked even when only the annual file is read."""
    path = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record()],
        compression=zipfile.ZIP_STORED,
    )
    with zipfile.ZipFile(path, 'a', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('extra.bin', b'extra payload')
    _corrupt_stored_member(path, member)
    stream = ZipFileReaderB3().iter_raw_lines(str(path))
    with pytest.raises(CorruptedZipError):
        next(stream)


def test_reader_revalidates_source_after_a_completed_pass(
    tmp_path: Path,
) -> None:
    """No path-based evidence cache may accept replaced source bytes."""
    path = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record()],
        compression=zipfile.ZIP_STORED,
    )
    reader = ZipFileReaderB3()
    assert len(list(reader.iter_raw_lines(str(path)))) == 3
    _corrupt_stored_member(path, 'COTAHIST_A2024.TXT')
    with pytest.raises(CorruptedZipError):
        next(reader.iter_raw_lines(str(path)))


def test_reader_rejects_member_replacement_before_yield(
    tmp_path: Path,
) -> None:
    """A valid replacement archive cannot change a preflighted member name."""
    path = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record()],
        member_name='COTAHIST.A2024',
    )
    with pytest.raises(ExtractionError, match='member changed'):
        next(
            ZipFileReaderB3().iter_raw_lines(
                str(path), expected_member='COTAHIST_A2024.TXT'
            )
        )


def test_reader_checks_extra_member_expansion_limits(tmp_path: Path) -> None:
    """Unused members remain subject to the same decompression budgets."""
    path = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('extra.bin', b'x' * 2000)
    defaults = ArchiveSafetyLimits.from_environment()
    limits = replace(defaults, max_member_uncompressed_bytes=1000)
    with pytest.raises(CorruptedZipError):
        next(ZipFileReaderB3(limits=limits).iter_raw_lines(str(path)))
