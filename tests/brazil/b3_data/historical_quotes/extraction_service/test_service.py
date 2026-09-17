"""Transactional B3 scheduler integration tests."""

import asyncio
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    ExtractionServiceB3,
    ParquetWriterB3,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _service(mode: ProcessingModeEnumB3) -> ExtractionServiceB3:
    """Build a service with production collaborators for integration proof."""
    return ExtractionServiceB3(
        zip_reader=ZipFileReaderB3(),
        parser=CotahistParserB3(),
        processing_mode=mode,
    )


@pytest.mark.asyncio
async def test_fast_scheduler_merges_sources_in_deterministic_input_order(
    tmp_path: Path,
) -> None:
    """Completion order cannot alter the externally persisted row order."""
    first = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(ticker='PETR4')],
    )
    second = write_cotahist_txt(
        tmp_path,
        year=2025,
        records=[build_cotahist_record(year=2025, ticker='VALE3')],
    )
    output = tmp_path / 'quotes.parquet'

    result = await _service(ProcessingModeEnumB3.FAST).extract_from_zip_files(
        {str(second), str(first)}, {'010'}, output
    )

    assert result == {
        'total_files': 2,
        'success_count': 2,
        'error_count': 0,
        'total_records': 2,
        'errors': {},
        'output_file': str(output),
    }
    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


@pytest.mark.asyncio
async def test_all_filtered_sources_publish_an_empty_valid_parquet(
    tmp_path: Path,
) -> None:
    """A filter miss is a successful extraction, not a partial error."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(market='070')],
    )
    output = tmp_path / 'quotes.parquet'

    result = await _service(ProcessingModeEnumB3.SLOW).extract_from_zip_files(
        {str(source)}, {'010'}, output
    )

    assert result['success_count'] == 1
    assert result['error_count'] == 0
    assert result['total_records'] == 0
    assert pq.ParquetFile(output).metadata.num_rows == 0


@pytest.mark.asyncio
async def test_one_source_reuses_its_validated_staged_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One source must not be read and rewritten solely to perform a merge."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(ticker='PETR4')],
    )
    output = tmp_path / 'quotes.parquet'

    def unexpected_merge(*_args: object, **_kwargs: object) -> int:
        pytest.fail('A single validated source must bypass the merge writer')

    monkeypatch.setattr(
        extraction_service.service,
        'merge_temp_files_streaming',
        unexpected_merge,
    )

    result = await _service(ProcessingModeEnumB3.SLOW).extract_from_zip_files(
        {str(source)}, {'010'}, output
    )

    assert result['total_records'] == 1
    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == ['PETR4']


@pytest.mark.asyncio
async def test_source_failure_keeps_previous_final_output_and_all_inputs(
    tmp_path: Path,
) -> None:
    """A malformed selected record rolls the whole batch back."""
    valid = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(ticker='PETR4')],
    )
    malformed = write_cotahist_txt(
        tmp_path,
        year=2025,
        records=[build_cotahist_record(year=2025)[:244]],
    )
    output = tmp_path / 'quotes.parquet'
    await ParquetWriterB3().write_to_parquet([], output)
    before = output.read_bytes()

    result = await _service(ProcessingModeEnumB3.FAST).extract_from_zip_files(
        {str(valid), str(malformed)}, {'010'}, output
    )

    assert result['success_count'] == 0
    assert result['error_count'] >= 1
    assert result['total_records'] == 0
    assert result['output_file'] == ''
    assert output.read_bytes() == before
    assert valid.exists() and malformed.exists()
    assert list(tmp_path.glob('.globaldatafinance-transaction-*')) == []


@pytest.mark.asyncio
async def test_cancellation_aborts_transaction_and_preserves_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelled extraction leaves no lock and permits a later retry."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(ticker='PETR4')],
    )
    output = tmp_path / 'quotes.parquet'
    output.write_bytes(b'previous output')
    previous_output = output.read_bytes()
    service = _service(ProcessingModeEnumB3.SLOW)
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def block_source_run(*_args: object, **_kwargs: object) -> None:
        entered.set()
        await blocked.wait()

    monkeypatch.setattr(service, '_run_sources', block_source_run)
    extraction = asyncio.create_task(
        service.extract_from_zip_files({str(source)}, {'010'}, output)
    )

    await asyncio.wait_for(entered.wait(), timeout=1)
    extraction.cancel()

    with pytest.raises(asyncio.CancelledError):
        await extraction

    assert list(tmp_path.glob('.globaldatafinance-transaction-*')) == []
    assert not (tmp_path / '.globaldatafinance-transaction.lock').exists()
    assert source.exists()
    assert output.read_bytes() == previous_output

    result = await _service(ProcessingModeEnumB3.SLOW).extract_from_zip_files(
        {str(source)}, {'010'}, output
    )

    assert result['success_count'] == 1
    assert result['error_count'] == 0
    assert output.exists()
