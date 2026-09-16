"""Opt-in B3 real-data checks using Arrow-only logical comparisons."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from globaldatafinance import ExtractionResultB3, HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from tests.support.builders import write_cotahist_zip

pytestmark = [pytest.mark.integration, pytest.mark.real_data]

_SAMPLE_RECORD_COUNT = 20_000
_FULL_TABLE_COMPARE_LIMIT_BYTES = 256 * 1024 * 1024
_DIGEST_BATCH_SIZE = 100_000
_DIGEST_MODULUS = 1 << 256


async def _extract_local_data(
    input_directory: Path,
    output_directory: Path,
    year: int,
    mode: str,
    output_name: str,
) -> ExtractionResultB3:
    """Run one caller-selected local year through the asynchronous facade."""
    return await HistoricalQuotesB3().extract_async(
        path_of_docs=str(input_directory),
        assets_list=['ações'],
        initial_year=year,
        last_year=year,
        destination_path=str(output_directory),
        output_filename=output_name,
        processing_mode=mode,
        verbose=False,
    )


def _assert_successful_result(
    result: ExtractionResultB3, output_directory: Path, output_name: str
) -> Path:
    """Assert the stable public result and return its output artifact."""
    output_path = output_directory / f'{output_name}.parquet'
    assert result['success'] is True
    assert result['total_files'] == result['success_count'] == 1
    assert result['error_count'] == 0
    assert result['total_records'] > 0
    assert result['errors'] == {}
    assert Path(result['output_file']) == output_path
    assert output_path.is_file()
    return output_path


@pytest.mark.asyncio
async def test_real_cotahist_catalog_resolves_one_line_per_available_input(
    local_cotahist_catalog: dict[int, list[Path]],
) -> None:
    """ZIP and TXT catalogs remain readable without loading an annual table."""
    reader = ZipFileReaderB3()
    inspected = 0
    for year, paths in sorted(local_cotahist_catalog.items()):
        for path in paths:
            assert path.name.casefold().startswith(f'cotahist_a{year}')
            iterator = reader.iter_lines(str(path))
            _line, context = next(iterator)
            assert context.source_basename == path.name
            inspected += 1
    assert inspected >= 1


@pytest.mark.asyncio
@pytest.mark.slow
async def test_real_cotahist_limited_sample_has_fast_slow_arrow_parity(
    local_cotahist: tuple[Path, int], tmp_path: Path
) -> None:
    """A real subset preserves all Arrow columns and logical values."""
    input_file, year = local_cotahist
    sample_input = tmp_path / 'sample-input'
    sample_input.mkdir()
    write_cotahist_zip(
        sample_input,
        year=year,
        records=_collect_quote_sample(input_file),
        compression=zipfile.ZIP_STORED,
    )
    fast = await _extract_local_data(
        sample_input, tmp_path / 'fast', year, 'fast', 'sample'
    )
    slow = await _extract_local_data(
        sample_input, tmp_path / 'slow', year, 'slow', 'sample'
    )
    fast_path = _assert_successful_result(fast, tmp_path / 'fast', 'sample')
    slow_path = _assert_successful_result(slow, tmp_path / 'slow', 'sample')

    fast_table = pq.read_table(fast_path)
    slow_table = pq.read_table(slow_path)
    assert fast_table.schema == parquet_writer.build_b3_schema()
    assert fast_table.num_rows <= _SAMPLE_RECORD_COUNT
    assert fast_table.equals(slow_table, check_metadata=False)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_real_cotahist_full_year_fast_has_stable_arrow_contract(
    local_cotahist: tuple[Path, int], tmp_path: Path
) -> None:
    """The annual opt-in run validates schema and streaming aggregate facts."""
    input_file, year = local_cotahist
    result = await _extract_local_data(
        input_file.parent, tmp_path / 'annual-fast', year, 'fast', 'annual'
    )
    output = _assert_successful_result(
        result, tmp_path / 'annual-fast', 'annual'
    )

    parquet = pq.ParquetFile(output)
    summary = _summary(parquet)
    assert parquet.schema_arrow == parquet_writer.build_b3_schema()
    assert summary['row_count'] == result['total_records']
    assert summary['first_date'].year == year
    assert summary['last_date'].year == year


@pytest.mark.asyncio
@pytest.mark.slow
async def test_real_cotahist_full_year_fast_slow_have_same_digest(
    local_cotahist: tuple[Path, int], tmp_path: Path
) -> None:
    """Large parity uses a bounded digest for large tables."""
    input_file, year = local_cotahist
    fast = await _extract_local_data(
        input_file.parent, tmp_path / 'fast', year, 'fast', 'full'
    )
    slow = await _extract_local_data(
        input_file.parent, tmp_path / 'slow', year, 'slow', 'full'
    )
    fast_path = _assert_successful_result(fast, tmp_path / 'fast', 'full')
    slow_path = _assert_successful_result(slow, tmp_path / 'slow', 'full')

    assert fast['total_records'] == slow['total_records']
    assert pq.ParquetFile(fast_path).schema_arrow == (
        parquet_writer.build_b3_schema()
    )
    max_output_size = max(fast_path.stat().st_size, slow_path.stat().st_size)
    if max_output_size <= _FULL_TABLE_COMPARE_LIMIT_BYTES:
        assert pq.read_table(fast_path).equals(
            pq.read_table(slow_path), check_metadata=False
        )
    else:
        assert _canonical_digest(fast_path) == _canonical_digest(slow_path)


def _collect_quote_sample(input_file: Path) -> list[str]:
    """Read a bounded collection of real type-01 lines for parity."""
    records: list[str] = []
    for line, _context in ZipFileReaderB3().iter_lines(str(input_file)):
        if line.startswith('01'):
            records.append(line)
            if len(records) == _SAMPLE_RECORD_COUNT:
                break
    assert records, f'{input_file} contains no type-01 records for parity'
    return records


def _summary(parquet: pq.ParquetFile) -> dict[str, Any]:
    """Compute aggregate date facts without materializing an annual table."""
    first_date = None
    last_date = None
    row_count = 0
    for batch in parquet.iter_batches(batch_size=_DIGEST_BATCH_SIZE):
        dates = batch.column('data_pregao').to_pylist()
        row_count += batch.num_rows
        current_first = min(dates)
        current_last = max(dates)
        first_date = (
            current_first
            if first_date is None
            else min(first_date, current_first)
        )
        last_date = (
            current_last if last_date is None else max(last_date, current_last)
        )
    assert first_date is not None and last_date is not None
    return {
        'row_count': row_count,
        'first_date': first_date,
        'last_date': last_date,
    }


def _canonical_digest(path: Path) -> str:
    """Hash batches in order, preserving schema and exact serialized values."""
    parquet = pq.ParquetFile(path)
    digest = hashlib.sha256(parquet.schema_arrow.to_string().encode('utf-8'))
    for batch in parquet.iter_batches(batch_size=_DIGEST_BATCH_SIZE):
        for row in batch.to_pylist():
            digest.update(
                json.dumps(
                    row,
                    default=str,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(',', ':'),
                ).encode('utf-8')
            )
    return digest.hexdigest()
