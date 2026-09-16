"""Public B3 facade integration tests for TXT and ZIP COTAHIST inputs."""

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('processing_mode', ['fast', 'slow'])
def test_public_extract_processes_plain_txt_with_canonical_schema(
    tmp_path: Path, processing_mode: str
) -> None:
    """The public facade preserves all B3 output fields for either mode."""
    input_dir = tmp_path / 'input'
    output_dir = tmp_path / 'output'
    input_dir.mkdir()
    write_cotahist_txt(
        input_dir,
        year=2024,
        records=[build_cotahist_record(ticker='PETR4')],
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(input_dir),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(output_dir),
        output_filename='quotes',
        processing_mode=processing_mode,
        verbose=False,
    )

    parquet = pq.ParquetFile(result['output_file'])
    assert result['success'] is True
    assert result['total_files'] == result['success_count'] == 1
    assert result['total_records'] == 1
    assert parquet.schema_arrow == parquet_writer.build_b3_schema()
    assert parquet.read()['ticker'].to_pylist() == ['PETR4']


def test_public_extract_treats_all_filtered_records_as_valid_empty_output(
    tmp_path: Path,
) -> None:
    """A requested asset miss is not an error or partial result."""
    input_dir = tmp_path / 'input'
    output_dir = tmp_path / 'output'
    input_dir.mkdir()
    write_cotahist_txt(
        input_dir,
        year=2024,
        records=[build_cotahist_record(market='070')],
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(input_dir),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(output_dir),
        output_filename='quotes',
        verbose=False,
    )

    assert result['success'] is True
    assert result['error_count'] == 0
    assert result['total_records'] == 0
    assert pq.ParquetFile(result['output_file']).metadata.num_rows == 0


def test_public_extract_accepts_historical_member_name_in_zip(
    tmp_path: Path,
) -> None:
    """The COTAHIST archive member compatibility contract is unchanged."""
    input_dir = tmp_path / 'input'
    output_dir = tmp_path / 'output'
    input_dir.mkdir()
    write_cotahist_zip(
        input_dir,
        year=2024,
        records=[build_cotahist_record(ticker='VALE3')],
        historical_member=True,
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(input_dir),
        assets_list=['ações'],
        initial_year=2024,
        last_year=2024,
        destination_path=str(output_dir),
        verbose=False,
    )

    assert result['success'] is True
    parquet = pq.ParquetFile(result['output_file'])
    assert parquet.read()['ticker'].to_pylist() == ['VALE3']


def test_fast_and_slow_modes_are_logically_equivalent(tmp_path: Path) -> None:
    """Scheduling changes cannot affect B3 schema, values, or row order."""
    input_dir = tmp_path / 'input'
    input_dir.mkdir()
    write_cotahist_txt(
        input_dir,
        year=2024,
        records=[
            build_cotahist_record(ticker='PETR4'),
            build_cotahist_record(ticker='VALE3'),
        ],
    )
    facade = HistoricalQuotesB3()
    common: dict[str, Any] = {
        'path_of_docs': str(input_dir),
        'assets_list': ['ações'],
        'initial_year': 2024,
        'last_year': 2024,
        'verbose': False,
    }
    fast = facade.extract(
        **common,
        destination_path=str(tmp_path / 'fast'),
        processing_mode='fast',
    )
    slow = facade.extract(
        **common,
        destination_path=str(tmp_path / 'slow'),
        processing_mode='slow',
    )

    assert fast['success'] and slow['success']
    assert (
        pq.ParquetFile(fast['output_file']).read()
        == pq.ParquetFile(slow['output_file']).read()
    )
