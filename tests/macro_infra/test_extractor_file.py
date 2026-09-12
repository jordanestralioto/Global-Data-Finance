import asyncio
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pyarrow.parquet as pq
import pytest

import globaldatafinance.macro_infra.extractor_file as extractor_file_module
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
)
from globaldatafinance.macro_infra import ExtractorAdapter

pytestmark = pytest.mark.unit


class TestExtractorListFilesInZip:
    def test_list_files_zip_not_found_raises_error(self, tmp_path):
        zip_path = tmp_path / 'nonexistent.zip'

        with pytest.raises(FileNotFoundError):
            ExtractorAdapter.list_files_in_zip(str(zip_path), '.txt')

    def test_list_files_corrupted_zip_raises_error(self, tmp_path):
        zip_path = tmp_path / 'corrupted.zip'
        zip_path.write_text('Not a ZIP')

        with pytest.raises(CorruptedZipError):
            ExtractorAdapter.list_files_in_zip(str(zip_path), '.txt')

    def test_list_files_no_filter_returns_all(self, tmp_path):
        zip_path = tmp_path / 'test.zip'

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('file1.txt', 'content')
            zf.writestr('file2.csv', 'data')
            zf.writestr('file3.json', '{}')

        files = ExtractorAdapter.list_files_in_zip(str(zip_path), '')

        assert len(files) == 3
        assert 'file1.txt' in files
        assert 'file2.csv' in files
        assert 'file3.json' in files

    def test_list_files_with_extension_filter(self, tmp_path):
        zip_path = tmp_path / 'test.zip'

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('file1.txt', 'content')
            zf.writestr('file2.csv', 'data')
            zf.writestr('file3.CSV', 'DATA')

        files = ExtractorAdapter.list_files_in_zip(str(zip_path), '.csv')

        assert len(files) == 2
        assert 'file2.csv' in files
        assert 'file3.CSV' in files

    def test_list_files_empty_zip_returns_empty(self, tmp_path):
        zip_path = tmp_path / 'empty.zip'

        with zipfile.ZipFile(zip_path, 'w') as _:
            pass

        files = ExtractorAdapter.list_files_in_zip(str(zip_path), '.txt')

        assert len(files) == 0


class TestExtractorOpenFileFromZip:
    def test_open_file_not_in_zip_raises_error(self, tmp_path):
        zip_path = tmp_path / 'test.zip'

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('other.txt', 'content')

        with zipfile.ZipFile(zip_path, 'r') as zf:
            with pytest.raises(ExtractionError) as exc_info:
                ExtractorAdapter.open_file_from_zip(zf, 'missing.txt')

            assert 'not found in ZIP' in str(exc_info.value)

    def test_open_file_successful(self, tmp_path):
        zip_path = tmp_path / 'test.zip'
        file_content = b'Test content'

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.txt', file_content)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            handle = ExtractorAdapter.open_file_from_zip(zf, 'data.txt')
            content = handle.read()
            handle.close()

        assert content == file_content


class TestExtractorReadTxtFromZipAsync:
    @pytest.mark.asyncio
    async def test_async_read_txt_file_not_found(self, tmp_path):
        zip_path = tmp_path / 'nonexistent.zip'
        extractor = ExtractorAdapter()

        with pytest.raises(FileNotFoundError):
            async for _ in extractor.extract_txt_from_zip_async(str(zip_path)):
                pass

    @pytest.mark.asyncio
    async def test_async_read_txt_corrupted_zip(self, tmp_path):
        zip_path = tmp_path / 'corrupted.zip'
        zip_path.write_text('Not a ZIP file')
        extractor = ExtractorAdapter()

        with pytest.raises(CorruptedZipError):
            async for _ in extractor.extract_txt_from_zip_async(str(zip_path)):
                pass

    @pytest.mark.asyncio
    async def test_async_read_txt_no_txt_file(self, tmp_path):
        zip_path = tmp_path / 'no_txt.zip'
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.csv', 'csv,data')

        with pytest.raises(ExtractionError):
            async for _ in extractor.extract_txt_from_zip_async(str(zip_path)):
                pass

    @pytest.mark.asyncio
    async def test_async_read_txt_successful(self, tmp_path):
        zip_path = tmp_path / 'async_txt.zip'
        txt_content = 'Line 1\nLine 2\nLine 3\n'
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.TXT', txt_content.encode('latin-1'))

        lines = []
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            lines.append(line)

        assert len(lines) == 3
        assert 'Line 1' in lines[0]
        assert 'Line 2' in lines[1]
        assert 'Line 3' in lines[2]

    @pytest.mark.asyncio
    async def test_async_read_txt_empty_file(self, tmp_path):
        zip_path = tmp_path / 'empty.zip'
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('empty.TXT', b'')

        lines = []
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            lines.append(line)

        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_async_read_txt_large_file(self, tmp_path):
        zip_path = tmp_path / 'large.zip'
        num_lines = 10000
        txt_content = '\n'.join([f'Line {i}' for i in range(num_lines)])
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('large.TXT', txt_content.encode('latin-1'))

        line_count = 0
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            line_count += 1
            if line_count % 1000 == 0:
                assert 'Line' in line

        assert line_count == num_lines

    @pytest.mark.asyncio
    async def test_async_read_txt_preserves_empty_lines_after_newline_removal(
        self, tmp_path
    ):
        zip_path = tmp_path / 'empty_lines.zip'
        txt_content = 'Line 1\n\nLine 3\n\n\nLine 6\n'
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.TXT', txt_content.encode('latin-1'))

        lines = []
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            lines.append(line)

        assert lines == ['Line 1', '', 'Line 3', '', '', 'Line 6']

    @pytest.mark.asyncio
    async def test_async_read_txt_handles_decode_errors(
        self, tmp_path, caplog
    ):
        _ = caplog
        zip_path = tmp_path / 'decode_error.zip'
        content = b'Valid line\n\x00\x01\x02\x03\nAnother line\n'
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.TXT', content)

        lines = []
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            lines.append(line)

        assert lines[0] == 'Valid line'
        assert lines[-1] == 'Another line'

    @pytest.mark.asyncio
    async def test_async_read_txt_partial_iteration(self, tmp_path):
        zip_path = tmp_path / 'partial.zip'
        txt_content = '\n'.join([f'Line {i}' for i in range(100)])
        extractor = ExtractorAdapter()

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.TXT', txt_content.encode('latin-1'))

        lines = []
        async for line in extractor.extract_txt_from_zip_async(str(zip_path)):
            lines.append(line)
            if len(lines) >= 10:
                break

        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_async_read_txt_wraps_unexpected_open_error(
        self, tmp_path, monkeypatch
    ):
        zip_path = tmp_path / 'unexpected.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('data.TXT', 'line\n')

        def fail_open(*_args, **_kwargs):
            raise RuntimeError('stream unavailable')

        monkeypatch.setattr(
            ExtractorAdapter,
            'open_file_from_zip',
            staticmethod(fail_open),
        )

        with pytest.raises(ExtractionError, match='stream unavailable'):
            async for _ in ExtractorAdapter().extract_txt_from_zip_async(
                str(zip_path)
            ):
                pass


class TestExtractorEdgeCases:
    @pytest.mark.asyncio
    async def test_concurrent_async_reads(self, tmp_path):
        zip_files = []
        for i in range(3):
            zip_path = tmp_path / f'file{i}.zip'
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('data.TXT', f'Content {i}\n'.encode('latin-1'))
            zip_files.append(str(zip_path))

        async def read_lines(zip_path):
            extractor = ExtractorAdapter()
            lines = []
            async for line in extractor.extract_txt_from_zip_async(zip_path):
                lines.append(line)
            return lines

        results = await asyncio.gather(*[read_lines(zp) for zp in zip_files])

        assert len(results) == 3
        for i, lines in enumerate(results):
            assert len(lines) >= 1
            assert f'Content {i}' in lines[0]


def _write_csv_archive(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('data.csv', b'first;second\n1;2\n')


def _patch_writer_failure(monkeypatch, output_path: Path, failure: Exception):
    def writer_factory(*_args, **_kwargs):
        output_path.write_bytes(b'partial parquet output')
        writer = Mock()
        writer.write_table.side_effect = failure
        return writer

    monkeypatch.setattr(
        extractor_file_module.pq, 'ParquetWriter', writer_factory
    )


def _patch_writer_close_failure(monkeypatch, output_path: Path) -> Mock:
    writer = Mock()

    def writer_factory(*_args, **_kwargs):
        output_path.write_bytes(b'partial parquet output')
        writer.close.side_effect = OSError('close failed')
        return writer

    monkeypatch.setattr(
        extractor_file_module.pq, 'ParquetWriter', writer_factory
    )
    return writer


class TestExtractorCsvToParquetSuccess:
    def test_public_extraction_writes_valid_parquet(self, tmp_path):
        archive_path = tmp_path / 'valid.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)

        with zipfile.ZipFile(archive_path) as archive:
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        parquet_file = pq.ParquetFile(output_path)
        assert parquet_file.metadata.num_rows == 1
        assert parquet_file.schema_arrow.names == ['first', 'second']

    def test_public_extraction_writes_empty_parquet_for_header_only_csv(
        self, tmp_path
    ):
        archive_path = tmp_path / 'empty.zip'
        output_path = tmp_path / 'empty.parquet'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            archive.writestr('empty.csv', b'first;second\n')

        with zipfile.ZipFile(archive_path) as archive:
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'empty.parquet',
                'empty.csv',
            )

        parquet_file = pq.ParquetFile(output_path)
        assert parquet_file.metadata.num_rows == 0
        assert parquet_file.metadata.num_columns == 2
        assert parquet_file.schema_arrow.names == ['first', 'second']


class TestExtractorCsvToParquetFailureHandling:
    def test_public_extraction_wraps_unexpected_encoding_error(
        self, tmp_path, monkeypatch
    ):
        archive_path = tmp_path / 'encoding_error.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)

        def fail_encoding(_zip_file, _csv_filename):
            raise RuntimeError('encoding unavailable')

        monkeypatch.setattr(
            extractor_file_module.ReadFilesAdapter,
            'read_csv_test_encoding',
            staticmethod(fail_encoding),
        )

        with (
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(
                ExtractionError, match='encoding unavailable'
            ) as exc_info,
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        assert not output_path.exists()
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_public_extraction_wraps_non_disk_write_oserror(
        self, tmp_path, monkeypatch
    ):
        archive_path = tmp_path / 'write_error.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)
        failure = OSError('permission denied')
        _patch_writer_failure(monkeypatch, output_path, failure)

        with (
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(
                ExtractionError, match='permission denied'
            ) as exc_info,
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        assert not output_path.exists()
        assert exc_info.value.__cause__ is failure

    def test_public_extraction_logs_writer_close_failure(
        self, tmp_path, monkeypatch, caplog
    ):
        archive_path = tmp_path / 'close_error.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)
        writer = _patch_writer_close_failure(monkeypatch, output_path)

        with (
            caplog.at_level('ERROR'),
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(ExtractionError, match='close failed'),
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        assert writer.close.call_count == 2
        assert any(
            'Failed to close writer' in record.message
            for record in caplog.records
        )
        assert not output_path.exists()

    def test_public_extraction_propagates_disk_full_and_cleans_partial_output(
        self, tmp_path, monkeypatch
    ):
        archive_path = tmp_path / 'disk_full.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)
        _patch_writer_failure(
            monkeypatch,
            output_path,
            OSError('No space left on device'),
        )

        with (
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(DiskFullError) as exc_info,
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        assert not output_path.exists()
        assert isinstance(exc_info.value.__cause__, OSError)
        assert 'No space left on device' in str(exc_info.value.__cause__)

    def test_public_extraction_retries_transient_output_deletion(
        self, tmp_path, monkeypatch
    ):
        archive_path = tmp_path / 'transient_delete.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)
        _patch_writer_failure(
            monkeypatch, output_path, ValueError('conversion failed')
        )
        original_unlink = Path.unlink
        unlink_attempts = 0

        def flaky_unlink(path: Path, missing_ok: bool = False) -> None:
            nonlocal unlink_attempts
            unlink_attempts += 1
            if unlink_attempts == 1:
                raise OSError('temporary filesystem lock')
            original_unlink(path, missing_ok=missing_ok)

        monkeypatch.setattr(Path, 'unlink', flaky_unlink)
        with (
            patch(
                'globaldatafinance.macro_infra.extractor_file.time.sleep'
            ) as sleep,
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(ExtractionError, match='conversion failed'),
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        assert unlink_attempts == 2
        sleep.assert_called_once_with(0.1)
        assert not output_path.exists()

    def test_public_extraction_reports_permanent_output_deletion_failure(
        self, tmp_path, monkeypatch
    ):
        archive_path = tmp_path / 'permanent_delete.zip'
        output_path = tmp_path / 'data.parquet'
        _write_csv_archive(archive_path)
        _patch_writer_failure(
            monkeypatch, output_path, ValueError('conversion failed')
        )

        def blocked_unlink(_path: Path, missing_ok: bool = False) -> None:
            _ = missing_ok
            raise OSError('permission denied')

        monkeypatch.setattr(Path, 'unlink', blocked_unlink)
        with (
            patch(
                'globaldatafinance.macro_infra.extractor_file.time.sleep'
            ) as sleep,
            zipfile.ZipFile(archive_path) as archive,
            pytest.raises(ExtractionError) as exc_info,
        ):
            ExtractorAdapter().extract_csv_from_zip_to_parquet(
                archive,
                output_path,
                'data.parquet',
                'data.csv',
            )

        message = str(exc_info.value)
        assert str(output_path) in message
        assert 'Cannot delete file after 3 attempts' in message
        assert isinstance(exc_info.value.__cause__, OSError)
        assert sleep.call_count == 2
        assert output_path.exists()
