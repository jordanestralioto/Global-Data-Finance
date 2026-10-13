import zipfile

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    AsyncDownloadAdapterCVM,
)


@pytest.mark.unit
class TestAsyncDownloadAdapterCVMFileValidation:
    @pytest.fixture
    def adapter(self):
        return AsyncDownloadAdapterCVM(
            file_extractor_repository=ParquetExtractorAdapterCVM(),
            max_concurrent=1,
        )

    def test_scenario_success_file_size_exact_match(self, adapter, tmp_path):
        test_file = tmp_path / 'test.zip'

        with zipfile.ZipFile(test_file, 'w') as zf:
            zf.writestr('test.csv', 'data,value\n1,2\n')

        expected_size = test_file.stat().st_size
        result = adapter._validate_downloaded_file(
            str(test_file), expected_size
        )

        assert result is True

    def test_scenario_error_even_small_file_size_mismatch(
        self, adapter, tmp_path
    ):
        test_file = tmp_path / 'test.zip'

        with zipfile.ZipFile(test_file, 'w') as zf:
            zf.writestr('test.csv', 'data\n' * 100)

        actual_size = test_file.stat().st_size
        expected_size = int(actual_size * 1.03)
        result = adapter._validate_downloaded_file(
            str(test_file), expected_size
        )

        assert result is False

    def test_scenario_error_file_size_outside_tolerance(
        self, adapter, tmp_path
    ):
        test_file = tmp_path / 'test.zip'

        with zipfile.ZipFile(test_file, 'w') as zf:
            zf.writestr('test.csv', 'data\n' * 100)

        actual_size = test_file.stat().st_size
        expected_size = int(actual_size * 1.10)
        result = adapter._validate_downloaded_file(
            str(test_file), expected_size
        )

        assert result is False

    def test_scenario_success_without_expected_size(self, adapter, tmp_path):
        test_file = tmp_path / 'test.zip'

        with zipfile.ZipFile(test_file, 'w') as zf:
            zf.writestr('test.csv', 'data\n')

        result = adapter._validate_downloaded_file(
            str(test_file), expected_size=None
        )

        assert result is True

    def test_scenario_success_valid_zip(self, adapter, tmp_path):
        test_file = tmp_path / 'valid.zip'

        with zipfile.ZipFile(test_file, 'w') as zf:
            zf.writestr('data.csv', 'column1,column2\nvalue1,value2\n')

        result = adapter._validate_downloaded_file(str(test_file))

        assert result is True

    def test_scenario_error_corrupted_zip(self, adapter, tmp_path):
        test_file = tmp_path / 'corrupted.zip'
        test_file.write_bytes(b'This is not a valid ZIP file')

        result = adapter._validate_downloaded_file(str(test_file))

        assert result is False

    def test_scenario_error_empty_zip(self, adapter, tmp_path):
        test_file = tmp_path / 'empty.zip'

        with zipfile.ZipFile(test_file, 'w'):
            pass

        result = adapter._validate_downloaded_file(str(test_file))

        assert result is False

    def test_scenario_error_nonexistent_file(self, adapter, tmp_path):
        test_file = tmp_path / 'nonexistent.zip'
        result = adapter._validate_downloaded_file(str(test_file))

        assert result is False
