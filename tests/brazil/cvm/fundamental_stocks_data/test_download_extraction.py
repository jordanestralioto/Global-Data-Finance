"""Regression tests for observable CVM extraction failures."""

import logging
import zipfile
from unittest.mock import MagicMock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)

pytestmark = pytest.mark.integration


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
