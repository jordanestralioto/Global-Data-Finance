import asyncio
import logging
import string
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    DownloadResultCVM,
    download_paths,
)
from globaldatafinance.core.config import ArchiveSafetySettings
from globaldatafinance.macro_exceptions import (
    DiskFullError,
    DownloadTimeoutError,
    ExtractionError,
    InvalidDestinationPathError,
    NetworkError,
    SecurityError,
)

pytestmark = pytest.mark.unit


_TEST_DATA_ALPHABET = string.ascii_letters + string.digits


def _large_test_data(size: int = 150_000) -> str:
    """Return deterministic payload large enough for file validation tests."""
    repeats = size // len(_TEST_DATA_ALPHABET) + 1
    return (_TEST_DATA_ALPHABET * repeats)[:size]


def _csv_test_data(rows: int = 200) -> str:
    """Return deterministic CSV data for extraction tests."""
    categories = ('A', 'B', 'C', 'D')
    body = '\n'.join(
        f'{index % 1000},{index / 100:.4f},'
        f'{categories[index % len(categories)]},{100 + index % 900}'
        for index in range(rows)
    )
    return f'col1,col2,col3,col4\n{body}'


@pytest.mark.unit
class TestHttpxAsyncDownloadAdapterInitialization:
    def test_init_with_default_values(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        assert adapter.max_concurrent == 10
        assert adapter.chunk_size == 8192
        assert adapter.max_retries == 5
        assert adapter.automatic_extractor is False
        assert adapter.file_extractor_repository is mock_extractor
        assert adapter.requests_adapter.timeout == 180.0

    def test_init_with_custom_values(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor,
            max_concurrent=20,
            chunk_size=16384,
            timeout=240.0,
            max_retries=7,
            initial_backoff=2.0,
            max_backoff=180.0,
            backoff_multiplier=3.0,
            http2=False,
            automatic_extractor=True,
        )

        assert adapter.max_concurrent == 20
        assert adapter.chunk_size == 16384
        assert adapter.max_retries == 7
        assert adapter.automatic_extractor is True
        assert adapter.requests_adapter.timeout == 240.0
        assert adapter.retry_strategy.initial_backoff == 2.0
        assert adapter.retry_strategy.max_backoff == 180.0
        assert adapter.retry_strategy.multiplier == 3.0

    def test_init_creates_requests_adapter(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        assert adapter.requests_adapter is not None
        assert hasattr(adapter.requests_adapter, 'async_download_file')

    def test_init_can_disable_redirect_following(self):
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=MagicMock(), follow_redirects=False
        )

        assert adapter.requests_adapter.follow_redirects is False

    def test_init_creates_retry_strategy(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        assert adapter.retry_strategy is not None
        assert hasattr(adapter.retry_strategy, 'is_retryable')
        assert hasattr(adapter.retry_strategy, 'calculate_backoff')

    def test_init_with_zero_max_concurrent(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_concurrent=0
        )

        assert adapter.max_concurrent == 0

    def test_init_with_very_high_concurrency(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_concurrent=1000
        )

        assert adapter.max_concurrent == 1000


@pytest.mark.unit
class TestHttpxAsyncDownloadAdapterHelpers:
    def test_download_target_uses_a_safe_url_basename(self, tmp_path):
        target = download_paths.build_download_target_path(
            'https://example.com/files/COTAHIST_A2023.ZIP?download=1#file',
            str(tmp_path),
        )

        assert target == tmp_path / 'COTAHIST_A2023.ZIP'

    @pytest.mark.parametrize('destination', ['', '   '])
    def test_download_target_rejects_empty_destination(self, destination):
        with pytest.raises(
            InvalidDestinationPathError,
            match='path cannot be empty or whitespace',
        ):
            download_paths.build_download_target_path(
                'https://example.com/files/COTAHIST_A2023.ZIP', destination
            )

    @pytest.mark.parametrize(
        'url',
        [
            'https://example.com/files/%2e%2e%2fescape.zip',
            'https://example.com/files/%2fetc%2fpasswd',
            'https://example.com/files/C%3A%5CWindows%5Csystem32',
            'https://example.com/files/sub\\escape.zip',
            'https://example.com/files/%00.zip',
        ],
    )
    def test_download_target_rejects_encoded_or_windows_path_components(
        self, tmp_path, url
    ):
        with pytest.raises(SecurityError):
            download_paths.build_download_target_path(url, str(tmp_path))


@pytest.mark.asyncio
class TestHttpxAsyncDownloadAdapterAsyncMethods:
    async def test_get_content_length_logs_head_failure_with_traceback(
        self, caplog
    ):
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=MagicMock()
        )
        adapter.requests_adapter.async_head = AsyncMock(
            side_effect=OSError('HEAD unavailable')
        )

        with caplog.at_level(logging.WARNING):
            result = await adapter._get_content_length(
                'https://example.com/file.zip'
            )

        assert result is None
        assert any(
            record.exc_info is not None
            and 'Failed to get Content-Length' in record.message
            for record in caplog.records
        )

    async def test_download_with_retry_success_first_attempt(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        async def mock_stream_download(_url, _filepath):
            pass

        adapter._stream_download = mock_stream_download

        success, error_msg = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert success is True
        assert error_msg is None

    async def test_download_with_retry_failure_after_retries(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_retries=2
        )

        async def mock_stream_download(_url, _filepath):
            raise NetworkError('DRE', 'Connection refused')

        adapter._stream_download = mock_stream_download

        success, error_msg = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert success is False
        assert error_msg is not None
        assert 'NetworkError' in error_msg

    async def test_download_with_retry_success_on_second_attempt(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_retries=3
        )

        call_count = 0

        async def mock_stream_download(_url, _filepath):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError('DRE', 'Temporary error')

        adapter._stream_download = mock_stream_download

        success, error_msg = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert success is True
        assert error_msg is None
        assert call_count == 2

    async def test_download_with_retry_non_retryable_error(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_retries=5
        )

        call_count = 0

        async def mock_stream_download(_url, _filepath):
            nonlocal call_count
            call_count += 1
            raise ValueError('Invalid URL format')

        adapter._stream_download = mock_stream_download

        success, error_msg = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert success is False
        assert error_msg is not None
        assert call_count == 1

    async def test_download_with_retry_timeout_error(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_retries=2
        )

        async def mock_stream_download(_url, _filepath):
            raise DownloadTimeoutError('DRE', 30.0)

        adapter._stream_download = mock_stream_download

        success, error_msg = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert success is False
        assert 'DownloadTimeoutError' in error_msg

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_with_retry_does_not_clean_final_path_on_failure(
        self, mock_remove
    ):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_retries=1
        )

        async def mock_stream_download(_url, _filepath):
            raise NetworkError('DRE', 'Error')

        adapter._stream_download = mock_stream_download

        await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        mock_remove.assert_not_called()

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.asyncio.sleep'
    )
    async def test_download_with_retry_backoff(self, mock_sleep):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor,
            max_retries=3,
            initial_backoff=1.0,
        )

        call_count = 0

        async def mock_stream_download(_url, _filepath):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError('DRE', 'Temporary')

        adapter._stream_download = mock_stream_download

        await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DRE',
            '2023',
        )

        assert mock_sleep.call_count >= 1

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.asyncio.sleep'
    )
    async def test_download_with_retry_translates_httpx_timeout_and_retries(
        self, mock_sleep
    ):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor,
            max_retries=2,
        )

        call_count = 0

        async def mock_stream_download(_url, _filepath):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ReadTimeout('')

        adapter._stream_download = mock_stream_download

        success, err = await adapter._download_with_retry(
            'https://example.com/file.zip',
            'test-data/file.zip',
            'DFP',
            '2012',
        )

        assert success is True
        assert err is None
        assert call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
class TestHttpxAsyncDownloadAdapterStreamDownload:
    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_stream_download_does_not_clean_final_path_on_error(
        self, mock_remove
    ):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        adapter.requests_adapter = MagicMock()
        adapter.requests_adapter.async_download_to_staging_file = AsyncMock(
            side_effect=NetworkError('DRE', 'Error')
        )

        with pytest.raises(NetworkError):
            await adapter._stream_download(
                'https://example.com/file.zip', 'test-data/file.zip'
            )

        mock_remove.assert_not_called()

    async def test_stream_download_calls_requests_adapter(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        adapter.requests_adapter = MagicMock()
        adapter.requests_adapter.async_download_to_staging_file = AsyncMock()

        await adapter._stream_download(
            'https://example.com/file.zip', 'test-data/file.zip'
        )

        adapter.requests_adapter.async_download_to_staging_file.assert_called_once_with(
            url='https://example.com/file.zip',
            output_path='test-data/file.zip',
            chunk_size=8192,
            max_bytes=ArchiveSafetySettings().max_archive_bytes,
        )

    async def test_stream_download_uses_custom_chunk_size(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, chunk_size=16384
        )

        adapter.requests_adapter = MagicMock()
        adapter.requests_adapter.async_download_to_staging_file = AsyncMock()

        await adapter._stream_download(
            'https://example.com/file.zip', 'test-data/file.zip'
        )

        adapter.requests_adapter.async_download_to_staging_file.assert_called_once_with(
            url='https://example.com/file.zip',
            output_path='test-data/file.zip',
            chunk_size=16384,
            max_bytes=ArchiveSafetySettings().max_archive_bytes,
        )


@pytest.mark.asyncio
class TestHttpxAsyncDownloadAdapterDownloadAndExtract:
    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_without_automatic_extractor(
        self, _mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()
        zip_path = output_dir / 'file.zip'

        # Use a deterministic payload above the 100 KB validation floor.
        random_data = _large_test_data()
        csv_data = _csv_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', csv_data)

        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=False
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None  # No Content-Length available

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
        )

        assert result.success_count_downloads == 1
        assert 'DRE_2023' in result.successful_downloads

        mock_extractor.extract.assert_not_called()

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_with_automatic_extractor(
        self, mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        random_data = _large_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        pq.write_table(
            pa.table({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']}),
            output_dir / 'file1.parquet',
        )
        pq.write_table(
            pa.table({'col3': [4, 5, 6], 'col4': ['d', 'e', 'f']}),
            output_dir / 'file2.parquet',
        )

        mock_extractor = MagicMock()

        def create_current_parquet(_source_path, _destination_path):
            pq.write_table(
                pa.table({'col': [1]}), output_dir / 'current.parquet'
            )

        mock_extractor.extract.side_effect = create_current_parquet
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        mock_extractor.extract.assert_called_once()
        assert mock_remove.called, (
            'ZIP source should be removed after successful extraction with '
            'parquet files'
        )
        assert result.success_count_downloads == 1

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_ignores_old_parquets_when_empty(
        self, mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        random_data = _large_test_data()
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('payload.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        pq.write_table(pa.table({'old': [1]}), output_dir / 'old.parquet')

        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        result = DownloadResultCVM()
        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            MagicMock(),
            automatic_extractor=True,
        )

        assert result.success_count_downloads == 0
        assert result.error_count_downloads == 1
        assert (
            'No parquet files generated' in result.failed_downloads['DRE_2023']
        )
        assert not mock_remove.called

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_no_parquet_files_keeps_zip(
        self, mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        # Use a deterministic payload above the 100 KB validation floor.
        random_data = _large_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        mock_extractor.extract.assert_called_once()
        assert not mock_remove.called, (
            'ZIP source should NOT be removed if no parquet files were created'
        )
        assert result.error_count_downloads == 1
        assert (
            'No parquet files generated' in result.failed_downloads['DRE_2023']
        )

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_extraction_error(
        self, _mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        # Use a deterministic payload above the 100 KB validation floor.
        random_data = _large_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = ExtractionError(
            'test-data/file.zip', 'Bad CSV'
        )

        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        assert result.error_count_downloads == 1
        assert 'DRE_2023' in result.failed_downloads
        assert 'ExtractionFailed' in result.failed_downloads['DRE_2023']

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_disk_full_error(
        self, mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        # Use a deterministic payload above the 100 KB validation floor.
        random_data = _large_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = DiskFullError('test-data/output')

        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        assert result.error_count_downloads == 1
        assert 'DiskFull' in result.failed_downloads['DRE_2023']
        assert not mock_remove.called
        assert zip_path.exists()

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.remove_file'
    )
    async def test_download_and_extract_unexpected_extraction_error(
        self, _mock_remove, tmp_path
    ):
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        zip_path = output_dir / 'file.zip'
        # Use a deterministic payload above the 100 KB validation floor.
        random_data = _large_test_data()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('test.txt', random_data)
            zf.writestr('data.csv', 'col1,col2\n1,2\n')

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = RuntimeError('Unexpected error')

        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        async def mock_get_content_length(_url):
            return None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = mock_get_content_length

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            str(output_dir),
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        assert result.error_count_downloads == 1
        assert 'UnexpectedError' in result.failed_downloads['DRE_2023']

    async def test_download_and_extract_download_failure(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=True
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return False, 'NetworkError: Connection refused'

        adapter._download_with_retry = mock_download_with_retry

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            'test-data/output',
            'DRE',
            '2023',
            result,
            mock_progress,
            automatic_extractor=True,
        )

        assert result.error_count_downloads == 1
        assert 'DRE_2023' in result.failed_downloads
        mock_extractor.extract.assert_not_called()

    async def test_download_and_extract_updates_progress(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, automatic_extractor=False
        )

        async def mock_download_with_retry(_url, _filepath, _doc_name, _year):
            return True, None

        adapter._download_with_retry = mock_download_with_retry
        adapter._get_content_length = AsyncMock(return_value=None)
        adapter._validate_downloaded_file = MagicMock(return_value=True)

        mock_progress = MagicMock()
        result = DownloadResultCVM()

        await adapter._download_and_extract(
            'https://example.com/file.zip',
            'test-data/output',
            'DRE',
            '2023',
            result,
            mock_progress,
        )

        mock_progress.update.assert_called_once_with(1)


@pytest.mark.asyncio
class TestHttpxAsyncDownloadAdapterConcurrency:
    async def test_run_downloads_respects_semaphore(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor, max_concurrent=2
        )

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_download_and_extract(*_args, **_kwargs):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                if concurrent_count > max_concurrent:
                    max_concurrent = concurrent_count

            await asyncio.sleep(0.01)

            async with lock:
                concurrent_count -= 1

        adapter._download_and_extract = mock_download_and_extract

        tasks = [
            (
                f'https://example.com/file{i}.zip',
                'DRE',
                '2023',
                'test-data/output',
            )
            for i in range(10)
        ]

        result = DownloadResultCVM()

        await adapter._run_downloads(tasks, result)

        assert max_concurrent <= 2

    async def test_run_downloads_with_empty_tasks(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        result = DownloadResultCVM()

        await adapter._run_downloads([], result)

        assert result.success_count_downloads == 0
        assert result.error_count_downloads == 0


@pytest.mark.unit
class TestHttpxAsyncDownloadAdapterEdgeCases:
    def test_adapter_with_none_extractor(self):
        adapter = AsyncDownloadAdapterCVM(file_extractor_repository=None)
        assert adapter.file_extractor_repository is None

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.http.asyncio.run'
    )
    def test_download_docs_delegates_to_asyncio_run(self, mock_asyncio_run):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )
        expected = DownloadResultCVM()
        mock_asyncio_run.return_value = expected

        tasks = [
            (
                'https://example.com/file.zip',
                'DRE',
                '2023',
                'test-data/output',
            )
        ]

        result = adapter.download_docs(tasks)

        # The sync wrapper returns whatever asyncio.run produces from
        # async_download_docs.
        assert result is expected
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args.args[0].close()


@pytest.mark.unit
class TestHttpxAsyncDownloadAdapterDownloadDocsRepository:
    def test_implements_download_docs_method(self):
        mock_extractor = MagicMock()
        adapter = AsyncDownloadAdapterCVM(
            file_extractor_repository=mock_extractor
        )

        assert hasattr(adapter, 'download_docs')
        assert callable(adapter.download_docs)
