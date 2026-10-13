"""Full-content validation and memory bounds for exact CVM output."""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    records,
    writer,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.integration


def _source(tmp_path: Path, contents: bytes) -> Path:
    """Write a locally owned ZIP fixture without compression expansion."""
    path = tmp_path / 'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', contents)
    return path


def test_readable_wrong_values_cannot_be_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matching headers and counts cannot conceal changed field contents."""
    source = _source(tmp_path, b'id;value\n0001;1.234567890123456789\n')
    source_bytes = source.read_bytes()
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    original_write = writer._write_row_group

    def corrupt_field(parquet_writer, batches, schema, output_path):
        table = pa.Table.from_batches(batches, schema=schema)
        table = table.set_column(
            1, schema.field(1), pa.array(['rounded value'], type=pa.string())
        )
        original_write(parquet_writer, table.to_batches(), schema, output_path)

    monkeypatch.setattr(writer, '_write_row_group', corrupt_field)
    with pytest.raises(ExtractionError, match='differs from the complete CSV'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert source.read_bytes() == source_bytes
    assert previous.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
    assert not (tmp_path / '.cvm-write-lock').exists()


def test_large_fields_preserve_text_without_global_csv_parser_mutation(
    tmp_path: Path,
) -> None:
    """A record exceeding Arrow's normal block survives bounded processing."""
    value = 'ação ' * 65_000
    field_limit_before = csv.field_size_limit()
    source = _source(tmp_path, f'value\n{value}\n'.encode())

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'value': value}
    ]
    assert csv.field_size_limit() == field_limit_before


def test_oversized_record_is_rejected_without_replacing_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resource limit produces an explicit failure with the source intact."""
    source = _source(tmp_path, b'value\n' + b'x' * 64 + b'\n')
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    monkeypatch.setattr(records, 'MAX_RECORD_BYTES', 32)

    with pytest.raises(ExtractionError, match='record exceeds 32'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert previous.read_bytes() == b'previous output'
    assert source.exists()


def test_wide_rows_use_a_byte_budget_for_row_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Long text records cannot accumulate fifty thousand large rows."""
    values = ['x' * 1024 + str(index) for index in range(100)]
    source = _source(tmp_path, ('value\n' + '\n'.join(values) + '\n').encode())
    monkeypatch.setattr(writer, 'ROW_GROUP_BYTES', 8192)

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    with pq.ParquetFile(tmp_path / 'data.parquet') as parquet:
        groups = [
            parquet.metadata.row_group(index)
            for index in range(parquet.metadata.num_row_groups)
        ]
        assert len(groups) > 1
        assert all(group.num_rows <= 7 for group in groups)
        assert sum(group.num_rows for group in groups) == 100
        assert parquet.read().column('value').to_pylist() == values


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'])
def test_every_supported_line_ending_preserves_fields_and_empty_records(
    tmp_path: Path, ending: str
) -> None:
    """LF, CRLF, and CR remain record separators without dropping blanks."""
    source = _source(
        tmp_path, ending.join(['id;value', '0001;N/A', '', '']).encode()
    )

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '0001', 'value': 'N/A'},
        {'id': '', 'value': ''},
    ]


def test_final_record_without_line_ending_preserves_its_fields(
    tmp_path: Path,
) -> None:
    """EOF terminates a complete final record without requiring a newline."""
    source = _source(tmp_path, b'id;value\n0007;N/A')
    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '0007', 'value': 'N/A'}
    ]


def test_exactly_full_row_group_never_creates_an_empty_trailing_group(
    tmp_path: Path,
) -> None:
    """The row-group boundary preserves every source row and its order."""
    values = [str(index) for index in range(50_000)]
    source = _source(tmp_path, ('value\n' + '\n'.join(values) + '\n').encode())
    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))
    with pq.ParquetFile(tmp_path / 'data.parquet') as parquet:
        assert parquet.metadata.num_row_groups == 1
        assert parquet.metadata.row_group(0).num_rows == 50_000
        assert parquet.read().column('value').to_pylist() == values
