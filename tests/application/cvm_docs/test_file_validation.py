import zipfile

import pytest

from globaldatafinance.brazil.cvm.ingestion.extract import CvmParquetExtractor
from globaldatafinance.brazil.cvm.ingestion.http import CvmDownloadAdapter


@pytest.mark.unit
class TestCvmDownloadAdapterFileValidation:
    @pytest.fixture
    def adapter(self):
        return CvmDownloadAdapter(
            file_extractor_repository=CvmParquetExtractor(),
            max_concurrent=1,
        )

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
