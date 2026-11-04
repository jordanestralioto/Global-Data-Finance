"""Regression tests for observable CVM extraction failures."""

import logging
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.ingestion import download_extraction
from globaldatafinance.brazil.cvm.ingestion.extract import CvmParquetExtractor
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)

pytestmark = pytest.mark.integration


class _WritingExtractor:
    def __init__(self, output_name: str) -> None:
        self.output_name = output_name

    def extract(self, source_path: str, destination_path: str) -> None:
        (Path(destination_path) / self.output_name).write_bytes(
            Path(source_path).read_bytes()
        )


class _UnexpectedOutputExtractor:
    def extract(self, source_path: str, destination_path: str) -> None:
        CvmParquetExtractor().extract(source_path, destination_path)
        table = pa.table({'id': ['unexpected']}).replace_schema_metadata(
            {b'cvm.source-archive': Path(source_path).name.encode('utf-8')}
        )
        pq.write_table(table, Path(destination_path) / 'obsolete.parquet')


@pytest.mark.parametrize(
    ('failure', 'result_marker'),
    [
        (DiskFullError('/output'), 'DiskFull:'),
        (CorruptedZipError('/input.zip', 'invalid'), 'CorruptedZIP:'),
        (
            ParquetWriteError('/output.parquet', 'permission denied'),
            'ParquetWrite:',
        ),
        (ExtractionError('/input.zip', 'failed'), 'ExtractionFailed:'),
    ],
)
def test_known_extraction_failures_log_traceback_and_preserve_results(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    result_marker: str,
) -> None:
    with zipfile.ZipFile(tmp_path / 'input.zip', 'w') as archive:
        archive.writestr('data.csv', b'id\n1\n')
    original_bytes = (tmp_path / 'input.zip').read_bytes()
    extractor = MagicMock()
    extractor.extract.side_effect = failure
    package_logger = logging.getLogger('globaldatafinance')
    monkeypatch.setattr(package_logger, 'propagate', True)

    with caplog.at_level('ERROR'):
        error_message = download_extraction.extract_downloaded_file(
            file_extractor_repository=extractor,
            filepath=str(tmp_path / 'input.zip'),
            dest_path=str(tmp_path),
            doc_name='DFP',
            year='2024',
        )

    assert error_message is not None
    assert result_marker in error_message
    assert (tmp_path / 'input.zip').read_bytes() == original_bytes
    extractor.extract.assert_called_once_with(
        str(tmp_path / 'input.zip'), str(tmp_path)
    )
    assert any(record.exc_info is not None for record in caplog.records)


def test_obsolete_outputs_prevent_supplied_extractor_side_effects(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'input.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', b'id\n1\n')
    original = source.read_bytes()
    existing = tmp_path / 'data.parquet'
    existing.write_bytes(b'previous output')
    foreign = tmp_path / 'foreign.parquet'
    foreign.write_bytes(b'caller data')
    obsolete = tmp_path / 'obsolete.parquet'
    table = pa.table({'id': ['old']}).replace_schema_metadata(
        {b'cvm.source-archive': source.name.encode('utf-8')}
    )
    pq.write_table(table, obsolete)
    obsolete_bytes = obsolete.read_bytes()

    error = download_extraction.extract_downloaded_file(
        _WritingExtractor('collaborator-invoked.txt'),
        str(source),
        str(tmp_path),
        'CUSTOM',
        '1999',
    )

    assert error is not None
    assert 'Obsolete CVM artifacts' in error
    assert not (tmp_path / 'collaborator-invoked.txt').exists()
    assert source.read_bytes() == original
    assert existing.read_bytes() == b'previous output'
    assert obsolete.read_bytes() == obsolete_bytes
    assert foreign.read_bytes() == b'caller data'


def test_supplied_extractor_outputs_still_follow_source_inventory(
    tmp_path: Path,
) -> None:
    source = tmp_path / 'input.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('data.csv', b'id\n1\n')
    original = source.read_bytes()
    foreign = tmp_path / 'caller.txt'
    foreign.write_bytes(b'caller data')
    obsolete = tmp_path / 'obsolete.parquet'

    error = download_extraction.extract_downloaded_file(
        _UnexpectedOutputExtractor(),
        str(source),
        str(tmp_path),
        'CUSTOM',
        '1999',
    )

    assert error is not None
    assert 'Obsolete CVM artifacts' in error
    assert pq.read_table(obsolete).to_pylist() == [{'id': 'unexpected'}]
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '1'}
    ]
    assert source.read_bytes() == original
    assert foreign.read_bytes() == b'caller data'
