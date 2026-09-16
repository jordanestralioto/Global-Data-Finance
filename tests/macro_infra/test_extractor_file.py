"""Generic archive utilities after CVM moved CSV conversion to its owner."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    ExtractionError,
)
from globaldatafinance.macro_infra import ExtractorAdapter

pytestmark = pytest.mark.integration


def _archive(path: Path, members: dict[str, bytes | str]) -> None:
    """Create a small deterministic archive for boundary-level checks."""
    with zipfile.ZipFile(path, 'w') as zip_file:
        for name, contents in members.items():
            zip_file.writestr(name, contents)


def test_list_files_validates_and_filters_archive_members(
    tmp_path: Path,
) -> None:
    """Shared listing remains case-insensitive without parsing CSV payloads."""
    archive = tmp_path / 'documents.zip'
    _archive(
        archive,
        {'first.TXT': 'a', 'second.csv': 'b', 'nested/third.txt': 'c'},
    )

    assert ExtractorAdapter.list_files_in_zip(str(archive), '.txt') == [
        'first.TXT',
        'nested/third.txt',
    ]


def test_list_files_reports_missing_and_corrupted_archives(
    tmp_path: Path,
) -> None:
    """Archive faults retain their original source context."""
    missing = tmp_path / 'missing.zip'
    malformed = tmp_path / 'malformed.zip'
    malformed.write_text('not a zip', encoding='utf-8')

    with pytest.raises(FileNotFoundError):
        ExtractorAdapter.list_files_in_zip(str(missing), '.txt')
    with pytest.raises(CorruptedZipError):
        ExtractorAdapter.list_files_in_zip(str(malformed), '.txt')


def test_open_file_from_zip_uses_a_bounded_validated_member(
    tmp_path: Path,
) -> None:
    """The shared primitive only opens selected safe archive members."""
    archive_path = tmp_path / 'documents.zip'
    _archive(archive_path, {'data.txt': b'payload'})

    with zipfile.ZipFile(archive_path) as archive:
        open_member = ExtractorAdapter.open_file_from_zip
        with open_member(archive, 'data.txt') as source:
            assert source.read() == b'payload'
        with pytest.raises(ExtractionError, match='not found in ZIP'):
            ExtractorAdapter.open_file_from_zip(archive, 'missing.txt')


@pytest.mark.asyncio
async def test_async_text_reader_preserves_blank_lines_and_removes_newlines(
    tmp_path: Path,
) -> None:
    """Generic TXT iteration keeps semantic empty records for its callers."""
    archive = tmp_path / 'documents.zip'
    _archive(archive, {'data.TXT': b'first\r\n\r\nlast\n'})

    lines = [
        line
        async for line in ExtractorAdapter().extract_txt_from_zip_async(
            str(archive)
        )
    ]

    assert lines == ['first', '', 'last']


@pytest.mark.asyncio
async def test_async_text_reader_rejects_archives_without_a_txt_member(
    tmp_path: Path,
) -> None:
    """A generic TXT request never guesses a CSV member as text input."""
    archive = tmp_path / 'documents.zip'
    _archive(archive, {'data.csv': 'first;second\n'})

    with pytest.raises(ExtractionError, match=r'No \.TXT file'):
        async for _ in ExtractorAdapter().extract_txt_from_zip_async(
            str(archive)
        ):
            pass


def test_legacy_csv_to_parquet_method_is_not_a_generic_archive_api() -> None:
    """CVM owns its Arrow CSV pipeline instead of a shared pandas path."""
    assert not hasattr(ExtractorAdapter, 'extract_csv_from_zip_to_parquet')
