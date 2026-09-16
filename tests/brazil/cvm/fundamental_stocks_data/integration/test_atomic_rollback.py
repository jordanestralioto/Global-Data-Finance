"""CVM-owned failure-atomic ZIP extraction regressions."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import transaction
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    SecurityError,
)

pytestmark = pytest.mark.integration


def _write_archive(path: Path, members: dict[str, bytes]) -> Path:
    """Create a ZIP whose CSV values use the production semicolon dialect."""
    with zipfile.ZipFile(path, 'w') as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    return path


def _transaction_state(destination: Path) -> list[Path]:
    """Find only the private files and directories a transaction may leave."""
    return list(destination.glob('.globaldatafinance-transaction-*'))


def test_corrupted_input_preserves_existing_output_and_never_stages(
    tmp_path: Path,
) -> None:
    """Invalid archives cannot modify previous user-visible Parquet files."""
    destination = tmp_path / 'output'
    destination.mkdir()
    sentinel = destination / 'sentinel.parquet'
    sentinel.write_bytes(b'old bytes')
    expected = sentinel.read_bytes()
    source = tmp_path / 'corrupted.zip'
    source.write_bytes(b'not a ZIP archive')

    with pytest.raises(CorruptedZipError):
        ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert sentinel.read_bytes() == expected
    assert _transaction_state(destination) == []


def test_malformed_later_member_preserves_old_output_and_source_bytes(
    tmp_path: Path,
) -> None:
    """Conversion is entirely staged before the first public replacement."""
    destination = tmp_path / 'output'
    destination.mkdir()
    existing = destination / 'first.parquet'
    existing.write_bytes(b'old version')
    expected = hashlib.sha256(existing.read_bytes()).hexdigest()
    source = _write_archive(
        tmp_path / 'documents.zip',
        {
            'first.csv': b'version\nnew\n',
            'second.csv': b'version\nnew;too-wide\n',
        },
    )
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(ExtractionError, match='observed_fields=2'):
        ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert hashlib.sha256(existing.read_bytes()).hexdigest() == expected
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert not (destination / 'second.parquet').exists()
    assert _transaction_state(destination) == []


def test_disk_full_during_conversion_preserves_input_and_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A writer failure only removes derived staging, never the source ZIP."""
    destination = tmp_path / 'output'
    destination.mkdir()
    existing = destination / 'data.parquet'
    existing.write_bytes(b'old version')
    source = _write_archive(
        tmp_path / 'documents.zip', {'data.csv': b'value\nnew\n'}
    )

    def fail_convert(self: object, **_kwargs: object) -> object:
        _ = self
        raise DiskFullError(str(destination))

    monkeypatch.setattr(
        transaction.CvmCsvParquetPipeline, 'convert', fail_convert
    )

    with pytest.raises(DiskFullError):
        ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert existing.read_bytes() == b'old version'
    assert source.exists()
    assert _transaction_state(destination) == []


def test_successful_batch_replaces_conflicts_and_creates_new_outputs(
    tmp_path: Path,
) -> None:
    """A complete batch publishes all source results after validation."""
    destination = tmp_path / 'output'
    destination.mkdir()
    (destination / 'first.parquet').write_bytes(b'old bytes')
    source = _write_archive(
        tmp_path / 'documents.zip',
        {
            'first.csv': b'version\nnew\n',
            'second.csv': b'version\ncreated\n',
        },
    )

    ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert pq.read_table(destination / 'first.parquet').to_pylist() == [
        {'version': 'new'}
    ]
    assert pq.read_table(destination / 'second.parquet').to_pylist() == [
        {'version': 'created'}
    ]
    assert _transaction_state(destination) == []


def test_basename_collision_is_rejected_before_staging(
    tmp_path: Path,
) -> None:
    """Two members mapping to one basename cannot overwrite data."""
    source = _write_archive(
        tmp_path / 'collision.zip',
        {
            'one/data.csv': b'value\none\n',
            'two/data.csv': b'value\ntwo\n',
        },
    )

    with pytest.raises(ExtractionError, match='collide'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert not (tmp_path / 'data.parquet').exists()
    assert _transaction_state(tmp_path) == []


def test_reserved_unicode_member_is_rejected_before_crc_or_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Win32 device aliases fail before CRC, conversion, or publication."""
    destination = tmp_path / 'output'
    destination.mkdir()
    source = _write_archive(
        tmp_path / 'reserved-device.zip',
        {'COM¹.csv': b'code;value\n1;10\n'},
    )
    crc_called = False
    derive_called = False
    convert_called = False
    begin_called = False

    def fail_crc(*_args: object, **_kwargs: object) -> None:
        nonlocal crc_called
        crc_called = True
        raise AssertionError('CRC validation must follow name validation')

    def fail_derive(_self: object, _member: str) -> str:
        nonlocal derive_called
        derive_called = True
        raise AssertionError('Output derivation must follow name validation')

    def fail_convert(_self: object, **_kwargs: object) -> None:
        nonlocal convert_called
        convert_called = True
        raise AssertionError('Conversion must follow name validation')

    def fail_begin(_self: object, **_kwargs: object) -> object:
        nonlocal begin_called
        begin_called = True
        raise AssertionError('Publication must follow name validation')

    monkeypatch.setattr(transaction, 'validate_zip_crc_with_limits', fail_crc)
    monkeypatch.setattr(
        transaction.CvmFailureAtomicBatchCommit,
        '_parquet_basename',
        fail_derive,
    )
    monkeypatch.setattr(
        transaction.CvmCsvParquetPipeline, 'convert', fail_convert
    )
    monkeypatch.setattr(
        transaction.TransactionalPublisher, 'begin', fail_begin
    )

    with pytest.raises(CorruptedZipError, match=r'COM¹\.csv'):
        ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert crc_called is False
    assert derive_called is False
    assert convert_called is False
    assert begin_called is False
    assert not (destination / 'COM¹.parquet').exists()
    assert _transaction_state(destination) == []


def test_sensitive_destination_is_rejected_before_zip_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Destination validation precedes output discovery and archive reads."""
    source = _write_archive(
        tmp_path / 'source.zip', {'data.csv': b'value\n1\n'}
    )
    build_called = False

    def fail_build(self: object, zip_file: object) -> object:
        nonlocal build_called
        _ = (self, zip_file)
        build_called = True
        raise AssertionError('output discovery must not run')

    monkeypatch.setattr(
        transaction.CvmFailureAtomicBatchCommit,
        '_build_outputs',
        fail_build,
    )

    with zipfile.ZipFile(source) as archive, pytest.raises(SecurityError):
        transaction.CvmFailureAtomicBatchCommit(
            str(source), r'C:\Windows\System32'
        ).execute(archive)

    assert build_called is False
