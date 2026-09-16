"""COTAHIST member resolution and streaming parity regressions."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    ExtractionError,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


async def _read_all(reader: ZipFileReaderB3, path: Path) -> list[str]:
    """Collect one small bounded stream for exact line assertions."""
    return [line async for line in reader.read_lines_from_zip(str(path))]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('year', 'member_name'),
    [
        (2000, 'COTAHIST.A2000'),
        (2001, 'COTAHIST_A2001'),
        (2024, 'COTAHIST_A2024.TXT'),
    ],
)
async def test_reader_accepts_modern_and_historical_internal_member_layouts(
    tmp_path: Path, year: int, member_name: str
) -> None:
    """All supported modern and historical member names resolve explicitly."""
    record = build_cotahist_record(year=year, ticker=f'YEAR{year}')
    archive_path = write_cotahist_zip(
        tmp_path,
        year=year,
        records=[record],
        member_name=member_name,
    )

    lines = await _read_all(ZipFileReaderB3(), archive_path)

    assert lines == [record]


@pytest.mark.asyncio
async def test_reader_plain_txt_and_zip_preserve_identical_fixed_width_lines(
    tmp_path: Path,
) -> None:
    """Only CR/LF is removed; trailing spaces stay available to the parser."""
    record = build_cotahist_record(ticker='SPACES')
    txt_path = write_cotahist_txt(tmp_path, year=2024, records=[record])
    archive_path = write_cotahist_zip(tmp_path, year=2024, records=[record])
    reader = ZipFileReaderB3()

    txt_lines = await _read_all(reader, txt_path)
    zip_lines = await _read_all(reader, archive_path)

    assert txt_lines == [record]
    assert zip_lines == txt_lines
    assert len(zip_lines[0]) == 245
    assert zip_lines[0].endswith('001')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('external_year', 'members', 'reason'),
    [
        (2024, {'unrelated.TXT': b'not cotahist'}, 'No valid COTAHIST member'),
        (
            2024,
            {'COTAHIST_A2023.TXT': b'wrong year'},
            'does not match its internal member',
        ),
        (
            2024,
            {
                'COTAHIST_A2024.TXT': b'one',
                'COTAHIST.A2024': b'two',
            },
            'Ambiguous COTAHIST members',
        ),
        (
            2024,
            {'nested/COTAHIST_A2024.TXT': b'nested'},
            'No valid COTAHIST member',
        ),
    ],
)
async def test_reader_rejects_missing_ambiguous_nested_and_wrong_year_members(
    tmp_path: Path,
    external_year: int,
    members: dict[str, bytes],
    reason: str,
) -> None:
    """Only one root-level member whose year matches the archive is legal."""
    archive_path = tmp_path / f'COTAHIST_A{external_year}.ZIP'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)

    with pytest.raises(ExtractionError, match=reason):
        await _read_all(ZipFileReaderB3(), archive_path)


@pytest.mark.asyncio
async def test_reader_rejects_nonofficial_external_zip_filename(
    tmp_path: Path,
) -> None:
    """The B3 owner never guesses a COTAHIST year from arbitrary ZIP names."""
    archive_path = tmp_path / 'quotes.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('COTAHIST_A2024.TXT', b'content')

    with pytest.raises(ExtractionError, match='filename contract'):
        await _read_all(ZipFileReaderB3(), archive_path)


@pytest.mark.asyncio
async def test_reader_rejects_nonofficial_external_txt_filename(
    tmp_path: Path,
) -> None:
    """Plain text inputs keep the same official filename contract as ZIPs."""
    txt_path = tmp_path / 'quotes.txt'
    txt_path.write_text('01not-a-valid-record\n', encoding='latin-1')

    with pytest.raises(ExtractionError, match='filename contract'):
        await _read_all(ZipFileReaderB3(), txt_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('payload', 'reason'),
    [
        (b'', 'empty'),
        (b'00HEADER\n99TRAILER\n', 'no type-01 quote data record'),
    ],
)
async def test_reader_rejects_txt_without_quote_data_records(
    tmp_path: Path, payload: bytes, reason: str
) -> None:
    """A selected TXT cannot silently finish without a type-01 record."""
    txt_path = tmp_path / 'COTAHIST_A2024.TXT'
    txt_path.write_bytes(payload)

    with pytest.raises(ExtractionError, match=reason):
        await _read_all(ZipFileReaderB3(), txt_path)


@pytest.mark.asyncio
async def test_reader_rejects_corrupted_zip_before_parsing(
    tmp_path: Path,
) -> None:
    """Invalid archives raise a public error before yielding lines."""
    archive_path = tmp_path / 'COTAHIST_A2024.ZIP'
    archive_path.write_bytes(b'not zip data')

    with pytest.raises(CorruptedZipError):
        await _read_all(ZipFileReaderB3(), archive_path)


@pytest.mark.asyncio
async def test_reader_applies_shared_zip_policy_before_member_selection(
    tmp_path: Path,
) -> None:
    """B3 rejects unsafe archive metadata before it resolves COTAHIST names."""
    archive_path = tmp_path / 'COTAHIST_A2024.ZIP'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('../COTAHIST_A2024.TXT', b'unsafe')

    with pytest.raises(CorruptedZipError, match='unsafe ZIP member path'):
        await _read_all(ZipFileReaderB3(), archive_path)


@pytest.mark.asyncio
async def test_reader_does_not_schedule_a_coroutine_for_each_source_batch(
    tmp_path: Path,
) -> None:
    """The synchronous worker reader does not await while scanning lines."""
    records = [build_cotahist_record(ticker='BATCH')] * 8_193
    archive_path = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=records,
        compression=zipfile.ZIP_STORED,
    )
    lines = await _read_all(ZipFileReaderB3(), archive_path)

    assert len(lines) == 8_193
