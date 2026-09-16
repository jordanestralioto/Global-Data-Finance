"""Public CVM ZIP extraction through the source-owned Arrow pipeline."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    ExtractionError,
    SecurityError,
)

pytestmark = pytest.mark.integration


def _archive(path: Path, members: dict[str, bytes | str]) -> None:
    """Create a small CVM ZIP fixture with explicit archive member names."""
    with zipfile.ZipFile(path, 'w') as zip_file:
        for name, contents in members.items():
            zip_file.writestr(name, contents)


def test_public_extractor_publishes_one_or_more_arrow_outputs(
    tmp_path: Path,
) -> None:
    """Normal extraction preserves basename-only names and logical values."""
    archive = tmp_path / 'documents.zip'
    _archive(
        archive,
        {
            'nested/first.csv': b'code;value\n1;10\n',
            'second.csv': b'code;value\n2;20\n',
        },
    )

    ParquetExtractorAdapterCVM().extract(str(archive), str(tmp_path))

    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    assert pq.read_table(first).to_pylist() == [{'code': 1, 'value': 10}]
    assert pq.read_table(second).to_pylist() == [{'code': 2, 'value': 20}]
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()


def test_public_extractor_accepts_a_header_only_csv(tmp_path: Path) -> None:
    """A header-only source is a successful empty Parquet publication."""
    archive = tmp_path / 'documents.zip'
    _archive(archive, {'empty.csv': b'code;value\n'})

    ParquetExtractorAdapterCVM().extract(str(archive), str(tmp_path))

    parquet = pq.ParquetFile(tmp_path / 'empty.parquet')
    assert parquet.metadata.num_rows == 0
    assert parquet.schema_arrow.names == ['code', 'value']


def test_source_failure_leaves_old_outputs_and_zip_byte_for_byte_unchanged(
    tmp_path: Path,
) -> None:
    """A later malformed member cannot partially replace an existing batch."""
    archive = tmp_path / 'documents.zip'
    _archive(
        archive,
        {
            'a_good.csv': b'code;value\n1;10\n',
            'z_bad.csv': b'code;value\n2;20;30\n',
        },
    )
    old_output = tmp_path / 'a_good.parquet'
    old_output.write_bytes(b'old output bytes')
    old_hash = hashlib.sha256(old_output.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ExtractionError, match='observed_fields=3'):
        ParquetExtractorAdapterCVM().extract(str(archive), str(tmp_path))

    assert hashlib.sha256(old_output.read_bytes()).hexdigest() == old_hash
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == source_hash
    assert not (tmp_path / 'z_bad.parquet').exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_corrupted_or_empty_archives_never_create_outputs(
    tmp_path: Path,
) -> None:
    """Source corruption is diagnosed before a transaction opens staging."""
    corrupted = tmp_path / 'corrupted.zip'
    corrupted.write_text('not a ZIP', encoding='utf-8')
    empty = tmp_path / 'empty.zip'
    _archive(empty, {})

    with pytest.raises(CorruptedZipError):
        ParquetExtractorAdapterCVM().extract(str(corrupted), str(tmp_path))
    with pytest.raises(ExtractionError, match='does not contain any CSV'):
        ParquetExtractorAdapterCVM().extract(str(empty), str(tmp_path))

    assert not list(tmp_path.glob('*.parquet'))


def test_unsafe_destination_is_rejected_before_creating_transaction_state(
    tmp_path: Path,
) -> None:
    """Caller paths outside the approved safety policy remain blocked."""
    archive = tmp_path / 'documents.zip'
    _archive(archive, {'source.csv': b'code;value\n1;10\n'})

    with pytest.raises(SecurityError):
        ParquetExtractorAdapterCVM().extract(str(archive), '/')

    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_basename_collisions_are_rejected_before_writing_a_parquet(
    tmp_path: Path,
) -> None:
    """Two archive members cannot overwrite one output by path coincidence."""
    archive = tmp_path / 'documents.zip'
    _archive(
        archive,
        {
            'first/data.csv': b'code\n1\n',
            'second/data.csv': b'code\n2\n',
        },
    )

    with pytest.raises(ExtractionError, match='collide'):
        ParquetExtractorAdapterCVM().extract(str(archive), str(tmp_path))

    assert not list(tmp_path.glob('*.parquet'))
