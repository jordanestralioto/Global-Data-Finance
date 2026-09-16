"""Integration coverage for the CVM two-pass Arrow CSV pipeline."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    CvmCsvParquetPipeline,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    models as csv_models,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.integration


def _convert(
    tmp_path: Path,
    contents: bytes,
    *,
    member_name: str = 'source.csv',
) -> tuple[Path, csv_models.CsvPipelineResult]:
    """Write one ZIP member and run its pipeline inside private staging."""
    archive = tmp_path / 'source.zip'
    staging = tmp_path / 'staging'
    output = staging / 'source.parquet'
    staging.mkdir()
    with zipfile.ZipFile(archive, 'w') as zip_file:
        zip_file.writestr(member_name, contents)
    result = CvmCsvParquetPipeline(archive, member_name).convert(
        staged_path=output,
        staging_dir=staging,
    )
    return output, result


def test_global_inference_handles_a_decimal_after_the_first_row_group(
    tmp_path: Path,
) -> None:
    """Late decimals promote one complete column rather than one chunk only."""
    data_rows = [f'{index};{index}' for index in range(50_000)]
    data_rows.append('50000;1.5')
    output, result = _convert(
        tmp_path,
        ('id;value\n' + '\n'.join(data_rows) + '\n').encode(),
    )

    parquet = pq.ParquetFile(output)
    assert result.rows == 50_001
    assert result.row_groups == (50_000, 1)
    assert parquet.schema_arrow == pa.schema(
        [pa.field('id', pa.int64()), pa.field('value', pa.float64())]
    )
    assert parquet.read_row_group(1).to_pylist() == [
        {'id': 50_000, 'value': 1.5}
    ]


def test_header_only_csv_writes_empty_null_schema_without_pandas_metadata(
    tmp_path: Path,
) -> None:
    """Header-only regulatory files remain valid, explicit empty datasets."""
    output, result = _convert(tmp_path, b'first;second\n')

    parquet = pq.ParquetFile(output)
    assert result.rows == 0
    assert result.row_groups == ()
    assert parquet.metadata.num_rows == 0
    assert parquet.metadata.num_row_groups == 0
    assert parquet.schema_arrow == pa.schema(
        [pa.field('first', pa.null()), pa.field('second', pa.null())]
    )
    assert not parquet.schema_arrow.metadata


def test_cp1252_is_spooled_losslessly_and_quotes_remain_literal(
    tmp_path: Path,
) -> None:
    """The fixed QUOTE_NONE dialect preserves literal quote characters."""
    output, _ = _convert(
        tmp_path,
        b'name;note\nJo\xe3o;\x80 \x93quoted\x94\n',
    )

    assert pq.read_table(output).to_pylist() == [
        {'name': 'João', 'note': '€ “quoted”'}
    ]


def test_latin1_undefined_cp1252_bytes_are_preserved_losslessly(
    tmp_path: Path,
) -> None:
    """A CP1252 undefined byte chooses Latin-1 instead of replacement text."""
    output, _ = _convert(tmp_path, b'text\n\x81\n')

    assert pq.read_table(output).to_pylist() == [{'text': '\x81'}]


def test_boolean_inference_accepts_all_case_variants_globally(
    tmp_path: Path,
) -> None:
    """Mixed boolean casing is converted only after global classification."""
    output, _ = _convert(tmp_path, b'flag\nTrUe\nfAlSe\n')

    assert pq.read_table(output).to_pylist() == [
        {'flag': True},
        {'flag': False},
    ]


def test_short_and_blank_rows_are_padded_only_at_the_tail(
    tmp_path: Path,
) -> None:
    """Missing final fields become nulls while empty physical rows survive."""
    output, result = _convert(tmp_path, b'first;second;third\n1;2\n\n')

    assert result.rows == 2
    assert pq.read_table(output).to_pylist() == [
        {'first': 1.0, 'second': 2.0, 'third': None},
        {'first': None, 'second': None, 'third': None},
    ]


def test_one_column_blank_physical_row_is_preserved_as_a_null(
    tmp_path: Path,
) -> None:
    """A blank one-column record remains representable in QUOTE_NONE CSV."""
    output, result = _convert(tmp_path, b'value\n\n')

    assert result.rows == 1
    assert pq.read_table(output).to_pylist() == [{'value': None}]


def test_excess_fields_fail_with_source_context_and_never_write_output(
    tmp_path: Path,
) -> None:
    """A wider record cannot silently shift regulatory columns."""
    archive = tmp_path / 'source.zip'
    staging = tmp_path / 'staging'
    output = staging / 'source.parquet'
    staging.mkdir()
    with zipfile.ZipFile(archive, 'w') as zip_file:
        zip_file.writestr('source.csv', b'first;second\n1;2;3\n')

    with pytest.raises(
        ExtractionError, match='expected_fields=2; observed_fields=3'
    ):
        CvmCsvParquetPipeline(archive, 'source.csv').convert(
            staged_path=output,
            staging_dir=staging,
        )

    assert not output.exists()


def test_integer_boundaries_and_null_rules_choose_safe_explicit_types(
    tmp_path: Path,
) -> None:
    """Large integers are never rounded into floating-point representation."""
    output, _ = _convert(
        tmp_path,
        b'signed;unsigned;too_large\n-1;9223372036854775808;18446744073709551616\n',
    )

    assert pq.ParquetFile(output).schema_arrow == pa.schema(
        [
            pa.field('signed', pa.int64()),
            pa.field('unsigned', pa.uint64()),
            pa.field('too_large', pa.string()),
        ]
    )
    assert pq.read_table(output).to_pylist()[0]['too_large'] == (
        '18446744073709551616'
    )


def test_nullable_signed_integer_boundaries_remain_int64(
    tmp_path: Path,
) -> None:
    """Signed nullability must not promote lossless integers to doubles."""
    output, _ = _convert(
        tmp_path,
        b'value\n9223372036854775807\n-9223372036854775808\n\n',
    )

    parquet = pq.ParquetFile(output)
    assert parquet.schema_arrow == pa.schema([pa.field('value', pa.int64())])
    assert pq.read_table(output).to_pylist() == [
        {'value': 9223372036854775807},
        {'value': -9223372036854775808},
        {'value': None},
    ]


def test_mixed_integer_and_text_is_preserved_as_text(tmp_path: Path) -> None:
    """Incompatible scalar classes use a lossless string column."""
    output, _ = _convert(tmp_path, b'value\n9223372036854775807\nunknown\n')

    parquet = pq.ParquetFile(output)
    assert parquet.schema_arrow == pa.schema([pa.field('value', pa.string())])
    assert pq.read_table(output).to_pylist() == [
        {'value': '9223372036854775807'},
        {'value': 'unknown'},
    ]


def test_arbitrary_width_integer_is_preserved_as_text_without_python_int_limit(
    tmp_path: Path,
) -> None:
    """An integer beyond Python's digit guard stays lossless text."""
    oversized = '9' * 5_000
    output, _ = _convert(tmp_path, f'value\n{oversized}\n'.encode())

    parquet = pq.ParquetFile(output)
    assert parquet.schema_arrow == pa.schema([pa.field('value', pa.string())])
    assert pq.read_table(output).to_pylist() == [{'value': oversized}]
