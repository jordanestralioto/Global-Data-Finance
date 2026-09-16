"""Regression tests for observable CVM extraction failures."""

from unittest.mock import MagicMock

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    download_extraction,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('failure', 'result_marker', 'cleanup_expected'),
    [
        (DiskFullError('/output'), 'DiskFull:', False),
        (CorruptedZipError('/input.zip', 'invalid'), 'CorruptedZIP:', False),
        (ExtractionError('/input.zip', 'failed'), 'ExtractionFailed:', False),
    ],
)
def test_known_extraction_failures_log_traceback_and_preserve_results(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
    result_marker: str,
    cleanup_expected: bool,
) -> None:
    extractor = MagicMock()
    extractor.extract.side_effect = failure
    cleanup_file = MagicMock()
    result = DownloadResultCVM()

    with caplog.at_level('ERROR'):
        download_extraction.extract_downloaded_file(
            file_extractor_repository=extractor,
            filepath=str(tmp_path / 'input.zip'),
            dest_path=str(tmp_path),
            doc_name='DFP',
            year='2024',
            result=result,
            cleanup_file=cleanup_file,
        )

    assert result_marker in result.failed_downloads['DFP_2024']
    assert cleanup_file.called is cleanup_expected
    assert any(record.exc_info is not None for record in caplog.records)
