from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from tests.support.builders import csv_bytes, write_zip

pytestmark = pytest.mark.integration


def _write_archive(archive_path: Path, members: dict[str, list[str]]) -> None:
    write_zip(
        archive_path,
        {
            filename: csv_bytes(rows, encoding='latin-1')
            for filename, rows in members.items()
        },
    )


class TestEstablishedOverwriteSemantics:
    def test_same_csv_basename_replaces_existing_parquet(self, tmp_path):
        output_path = tmp_path / 'data.parquet'
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {'id': 1, 'value': 100, 'state': 'old'},
                    {'id': 2, 'value': 200, 'state': 'old'},
                ]
            ),
            output_path,
        )
        archive_path = tmp_path / 'replacement.zip'
        _write_archive(
            archive_path,
            {
                'data.csv': [
                    'id;value;state',
                    '10;900;new',
                    '20;800;new',
                    '30;700;new',
                ]
            },
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(archive_path), destination_path=str(tmp_path)
        )

        assert pq.read_table(output_path).to_pylist() == [
            {'id': 10, 'value': 900, 'state': 'new'},
            {'id': 20, 'value': 800, 'state': 'new'},
            {'id': 30, 'value': 700, 'state': 'new'},
        ]
        assert sorted(path.name for path in tmp_path.glob('*.parquet')) == [
            'data.parquet'
        ]

    def test_multiple_sequential_replacements_keep_latest_data(self, tmp_path):
        output_path = tmp_path / 'data.parquet'
        archives = [
            (
                'replacement_1.zip',
                ['version;value', '1;first'],
            ),
            (
                'replacement_2.zip',
                ['version;value', '2;last', '2;last'],
            ),
        ]

        for archive_name, rows in archives:
            archive_path = tmp_path / archive_name
            _write_archive(archive_path, {'data.csv': rows})
            ParquetExtractorAdapterCVM().extract(
                source_path=str(archive_path), destination_path=str(tmp_path)
            )

        assert pq.read_table(output_path).to_pylist() == [
            {'version': 2, 'value': 'last'},
            {'version': 2, 'value': 'last'},
        ]

    def test_different_csv_basenames_create_independent_outputs(
        self, tmp_path
    ):
        archive_path = tmp_path / 'independent_outputs.zip'
        _write_archive(
            archive_path,
            {
                'first.csv': ['asset;value', 'A;1'],
                'second.csv': ['asset;value', 'B;2', 'C;3'],
            },
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(archive_path), destination_path=str(tmp_path)
        )

        assert pq.read_table(tmp_path / 'first.parquet').to_pylist() == [
            {'asset': 'A', 'value': 1}
        ]
        assert pq.read_table(tmp_path / 'second.parquet').to_pylist() == [
            {'asset': 'B', 'value': 2},
            {'asset': 'C', 'value': 3},
        ]
        assert sorted(path.name for path in tmp_path.glob('*.parquet')) == [
            'first.parquet',
            'second.parquet',
        ]
