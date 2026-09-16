"""B3 source-worker tests for strict bounded Arrow artifacts."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def test_processor_writes_one_validated_temp_artifact_per_source(
    tmp_path: Path,
) -> None:
    """The worker holds no more than the configured Python record buffer."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(ticker='PETR4'),
            build_cotahist_record(ticker='VALE3'),
        ],
    )
    output = tmp_path / 'staging' / 'source.parquet'
    processor = extraction_service.ZipProcessorB3(
        ZipFileReaderB3(), python_record_limit=1
    )

    result = processor.process(source, {'010'}, output)

    assert result.temp_path == output
    assert result.selected_records == 2
    assert result.parsed_records == result.written_records == 2
    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


def test_processor_returns_no_temp_artifact_when_every_record_is_filtered(
    tmp_path: Path,
) -> None:
    """Valid but nonmatching records remain a successful zero-row source."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(market='070')],
    )
    output = tmp_path / 'staging' / 'filtered.parquet'

    result = extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
        source, {'010'}, output
    )

    assert result.temp_path is None
    assert result.metrics.filtered_records == 1
    assert result.written_records == 0
    assert output.exists() is False


def test_processor_removes_derived_temp_on_selected_record_failure(
    tmp_path: Path,
) -> None:
    """A malformed financial record cannot leave a publishable temp behind."""
    malformed = build_cotahist_record()[:244]
    source = write_cotahist_txt(tmp_path, year=2024, records=[malformed])
    output = tmp_path / 'staging' / 'broken.parquet'

    with pytest.raises(ExtractionError, match='Expected exactly 245'):
        extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
            source, {'010'}, output
        )

    assert output.exists() is False
    assert source.exists()
