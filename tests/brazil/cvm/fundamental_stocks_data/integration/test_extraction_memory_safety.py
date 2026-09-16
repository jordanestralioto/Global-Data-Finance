import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)

pytestmark = pytest.mark.integration


class TestMemorySafety:
    def test_small_csv_is_written_as_one_bounded_arrow_row_group(
        self, tmp_path: Path
    ) -> None:
        """The pipeline owns bounded Arrow groups instead of pandas chunks."""
        source_rows = [
            {'row_id': index, 'label': f'row-{index}', 'value': index * 1.5}
            for index in range(7)
        ]
        archive_path = tmp_path / 'multi_chunk.zip'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            archive.writestr(
                'multi_chunk.csv',
                'row_id;label;value\n'
                + ''.join(
                    f'{row["row_id"]};{row["label"]};{row["value"]}\n'
                    for row in source_rows
                ),
            )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(archive_path), destination_path=str(tmp_path)
        )

        output_path = tmp_path / 'multi_chunk.parquet'
        assert output_path.exists()
        parquet = pq.ParquetFile(output_path)
        assert parquet.metadata.num_rows == 7
        assert parquet.metadata.num_row_groups == 1
        assert pq.read_table(output_path).to_pylist() == source_rows
