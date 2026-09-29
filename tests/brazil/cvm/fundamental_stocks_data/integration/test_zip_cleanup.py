from pathlib import Path
from unittest.mock import Mock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)
from tests.support.builders import csv_bytes, write_zip

extract_downloaded_file = download_extraction.extract_downloaded_file

pytestmark = pytest.mark.integration


def _write_valid_archive(archive_path: Path) -> None:
    write_zip(
        archive_path,
        {
            'data.csv': csv_bytes(
                ['id;value', '1;10', '2;20', '3;30'],
                encoding='latin-1',
            )
        },
    )


def _delete_file(path: str) -> None:
    Path(path).unlink()


class TestZipCleanup:
    def test_successful_production_flow_removes_zip(self, tmp_path):
        archive_path = tmp_path / 'successful_download.zip'
        _write_valid_archive(archive_path)
        unprocessed_archives = [
            tmp_path / 'unprocessed_1.zip',
            tmp_path / 'unprocessed_2.zip',
        ]
        for unprocessed_archive in unprocessed_archives:
            unprocessed_archive.write_bytes(b'unprocessed')
        cleanup_calls: list[str] = []

        def cleanup(path: str) -> None:
            cleanup_calls.append(path)
            _delete_file(path)

        error_message = extract_downloaded_file(
            file_extractor_repository=ParquetExtractorAdapterCVM(),
            filepath=str(archive_path),
            dest_path=str(tmp_path),
            doc_name='DFP',
            year='2023',
            cleanup_file=cleanup,
        )

        assert error_message is None
        assert (tmp_path / 'data.parquet').exists()
        assert cleanup_calls == [str(archive_path)]
        assert not archive_path.exists()
        assert unprocessed_archives[0].exists()
        assert unprocessed_archives[1].exists()

    @pytest.mark.parametrize(
        ('failure_kind', 'failure'),
        [
            ('disk_full', DiskFullError('/output')),
            ('corrupted_zip', CorruptedZipError('/input.zip', 'invalid')),
            ('parquet_write', ParquetWriteError('/output.parquet', 'denied')),
        ],
    )
    def test_cleanup_failures_update_result_and_keep_source_zip(
        self, tmp_path, failure_kind, failure
    ):
        archive_path = tmp_path / f'{failure_kind}.zip'
        _write_valid_archive(archive_path)
        repository = Mock()
        repository.extract.side_effect = failure

        cleanup = Mock(side_effect=_delete_file)
        error_message = extract_downloaded_file(
            file_extractor_repository=repository,
            filepath=str(archive_path),
            dest_path=str(tmp_path),
            doc_name='DFP',
            year='2023',
            cleanup_file=cleanup,
        )

        assert error_message is not None
        expected_marker = {
            'disk_full': 'DiskFull:',
            'corrupted_zip': 'CorruptedZIP:',
            'parquet_write': 'ParquetWrite:',
        }[failure_kind]
        assert expected_marker in error_message
        assert str(failure) in error_message
        cleanup.assert_not_called()
        assert archive_path.exists()

    @pytest.mark.parametrize('error_kind', ['extraction', 'unexpected'])
    def test_non_cleanup_failures_keep_zip_for_investigation(
        self, tmp_path, error_kind
    ):
        archive_path = tmp_path / f'{error_kind}.zip'
        _write_valid_archive(archive_path)
        repository = Mock()
        if error_kind == 'extraction':
            repository.extract.side_effect = ExtractionError(
                str(archive_path), 'malformed CSV'
            )
        else:
            repository.extract.side_effect = RuntimeError('unexpected failure')

        cleanup = Mock(side_effect=_delete_file)
        error_message = extract_downloaded_file(
            file_extractor_repository=repository,
            filepath=str(archive_path),
            dest_path=str(tmp_path),
            doc_name='DFP',
            year='2023',
            cleanup_file=cleanup,
        )

        assert error_message is not None
        assert archive_path.exists()
        cleanup.assert_not_called()
