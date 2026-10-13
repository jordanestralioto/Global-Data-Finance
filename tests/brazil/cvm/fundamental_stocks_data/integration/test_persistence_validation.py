"""CVM page integrity and durability regressions with real Parquet I/O."""

from __future__ import annotations

import errno
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
    download_finalization,
    download_validation,
    transaction_io,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    source as csv_sources,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    writer as csv_writer,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import DiskFullError, ParquetWriteError
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
)

pytestmark = pytest.mark.integration


def _source_zip(path: Path) -> Path:
    """Create a small source with a stable integer and text schema."""
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', b'id;name\n1;first\n2;second\n')
    return path


def _corrupt_column_page(path: Path) -> None:
    """Flip one page byte while leaving the complete footer unchanged."""
    with pq.ParquetFile(path) as parquet:
        column = parquet.metadata.row_group(0).column(0)
        offset = column.dictionary_page_offset or column.data_page_offset
        position = offset + column.total_compressed_size - 1
    data = bytearray(path.read_bytes())
    data[position] ^= 0x40
    path.write_bytes(data)


def test_footer_valid_page_corruption_is_rejected_before_zip_cleanup(
    tmp_path: Path,
) -> None:
    """An intact footer cannot hide corrupted pages from the finalizer."""
    path = tmp_path / 'data.parquet'
    pq.write_table(
        pa.table({'id': [1, 2]}),
        path,
        compression='NONE',
        use_dictionary=False,
        write_page_checksum=True,
    )
    _corrupt_column_page(path)

    with pq.ParquetFile(path) as parquet:
        assert parquet.metadata.num_rows == 2
        assert parquet.schema_arrow == pa.schema([('id', pa.int64())])
    assert pq.read_table(path).to_pylist() != [{'id': 1}, {'id': 2}]
    assert (
        download_validation.validate_parquet_files([path], 'DFP', '2024')
        is False
    )


def test_staged_page_corruption_preserves_zip_and_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A data-page failure aborts before any old output is replaced."""
    source = _source_zip(tmp_path / 'source.zip')
    source_bytes = source.read_bytes()
    output = tmp_path / 'data.parquet'
    output.write_bytes(b'previous artifact')
    original = csv_writer.validate_parquet

    def corrupt_then_validate(
        csv_source: csv_sources.ReopenableCsvSource,
        path: Path,
        schema: pa.Schema,
        rows: int,
        row_groups: list[int],
    ) -> None:
        _corrupt_column_page(path)
        original(csv_source, path, schema, rows, row_groups)

    monkeypatch.setattr(csv_writer, 'validate_parquet', corrupt_then_validate)

    error = download_extraction.extract_downloaded_file(
        ParquetExtractorAdapterCVM(),
        str(source),
        str(tmp_path),
        'DFP',
        '2024',
    )

    assert error is not None
    assert 'ParquetWrite' in error
    assert source.read_bytes() == source_bytes
    assert output.read_bytes() == b'previous artifact'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_parquet_bytes_are_synced_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durable manifest updates never precede unsynced Parquet publication."""
    source = _source_zip(tmp_path / 'source.zip')
    events: list[tuple[str, str]] = []
    original_sync = FileOperations.fsync_file
    original_replace = transaction_io.CvmTransactionFileOperations.replace

    def record_sync(self: FileOperations, path: Path) -> None:
        if path.suffix == '.parquet':
            events.append(('sync', path.name))
        original_sync(self, path)

    def record_replace(
        self: transaction_io.CvmTransactionFileOperations,
        old: Path,
        new: Path,
    ) -> None:
        if new.suffix == '.parquet':
            events.append(('publish', new.name))
        original_replace(self, old, new)

    monkeypatch.setattr(FileOperations, 'fsync_file', record_sync)
    monkeypatch.setattr(
        transaction_io.CvmTransactionFileOperations, 'replace', record_replace
    )

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert events == [('sync', 'data.parquet'), ('publish', 'data.parquet')]
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '1', 'name': 'first'},
        {'id': '2', 'name': 'second'},
    ]


@pytest.mark.parametrize(
    ('error_number', 'expected_error'),
    [(errno.ENOSPC, DiskFullError), (errno.EIO, ParquetWriteError)],
)
def test_parquet_sync_failure_preserves_source_and_previous_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    expected_error: type[Exception],
) -> None:
    """Delayed write failures remain typed and never commit staged data."""
    source = _source_zip(tmp_path / 'source.zip')
    original_bytes = source.read_bytes()
    output = tmp_path / 'data.parquet'
    output.write_bytes(b'previous artifact')
    failure = OSError(error_number, 'injected fsync failure')
    original_sync = FileOperations.fsync_file

    def fail_parquet_sync(self: FileOperations, path: Path) -> None:
        if path.suffix == '.parquet':
            raise failure
        original_sync(self, path)

    monkeypatch.setattr(FileOperations, 'fsync_file', fail_parquet_sync)

    with pytest.raises(expected_error) as error:
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert error.value.__cause__ is failure
    assert source.read_bytes() == original_bytes
    assert output.read_bytes() == b'previous artifact'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_zip_sync_failure_preserves_existing_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged ZIP must be durable before replacing an existing download."""
    staging = _source_zip(tmp_path / 'source.zip.part')
    final = tmp_path / 'source.zip'
    final.write_bytes(b'previous download')
    original_sync = (
        download_finalization.DestinationFileOperationsCVM.fsync_file
    )

    def fail_zip_sync(
        self: download_finalization.DestinationFileOperationsCVM, path: Path
    ) -> None:
        if path == staging:
            raise OSError(errno.EIO, 'injected ZIP fsync failure')
        original_sync(self, path)

    monkeypatch.setattr(
        download_finalization.DestinationFileOperationsCVM,
        'fsync_file',
        fail_zip_sync,
    )

    result = download_finalization.finalize_downloaded_file(
        staging,
        final,
        str(tmp_path),
        'DFP',
        '2024',
        None,
        automatic_extractor=False,
        file_extractor_repository=None,
        validate_file=download_validation.validate_downloaded_file,
        cleanup_file=lambda filename: Path(filename).unlink(missing_ok=True),
    )

    assert result.succeeded is False
    assert 'ZIP fsync failure' in (result.error_message or '')
    assert final.read_bytes() == b'previous download'
    assert not staging.exists()
