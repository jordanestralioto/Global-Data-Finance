"""Opt-in resource measurement for the CVM streaming extractor."""

from __future__ import annotations

import zipfile
from importlib import import_module
from typing import Protocol, cast

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from tests.support.builders import csv_bytes


class _ProcessMemory(Protocol):
    rss: int


class _Process(Protocol):
    def memory_info(self) -> _ProcessMemory: ...


class _PsutilModule(Protocol):
    def Process(self) -> _Process: ...


psutil = cast(_PsutilModule, import_module('psutil'))


@pytest.mark.perf
@pytest.mark.slow
def test_large_cvm_csv_keeps_bounded_process_growth(tmp_path) -> None:
    """Measure the bounded-memory path with a deterministic large archive."""
    row_count = 100_000
    rows = ['row_id;label;value']
    rows.extend(
        f'{index};row-{index % 1000};{index * 1.5}'
        for index in range(row_count)
    )
    archive_path = tmp_path / 'large_memory_measurement.zip'
    with zipfile.ZipFile(
        archive_path, 'w', compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(
            'large_memory_measurement.csv',
            csv_bytes(rows, encoding='latin-1'),
        )

    process = psutil.Process()
    memory_before = process.memory_info().rss
    ParquetExtractorAdapterCVM().extract(
        source_path=str(archive_path), destination_path=str(tmp_path)
    )
    memory_after = process.memory_info().rss

    result = pq.ParquetFile(tmp_path / 'large_memory_measurement.parquet')
    memory_increase_mb = (memory_after - memory_before) / 1024**2

    assert result.metadata.num_rows == row_count
    assert memory_increase_mb < 150
