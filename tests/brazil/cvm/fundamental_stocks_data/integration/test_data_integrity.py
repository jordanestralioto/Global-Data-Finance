from __future__ import annotations

import math

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import csv_bytes, write_zip

pytestmark = pytest.mark.integration


class TestDataIntegrity:
    @pytest.fixture
    def sample_rows(self) -> list[dict[str, object]]:
        return [
            {'id': 1, 'name': 'Alice', 'value': 10.5, 'category': 'A'},
            {'id': 2, 'name': 'Bob', 'value': 20.3, 'category': 'B'},
            {'id': 3, 'name': 'Charlie', 'value': 30.7, 'category': 'A'},
            {'id': 4, 'name': 'David', 'value': 40.2, 'category': 'C'},
            {'id': 5, 'name': 'Eve', 'value': 50.9, 'category': 'B'},
        ]

    @pytest.fixture
    def csv_zip(self, tmp_path, sample_rows: list[dict[str, object]]):
        rows = ['id;name;value;category']
        rows.extend(
            f'{row["id"]};{row["name"]};{row["value"]};{row["category"]}'
            for row in sample_rows
        )
        return write_zip(
            tmp_path / 'data.zip',
            {'data.csv': csv_bytes(rows, encoding='latin-1')},
        )

    def test_no_data_loss_during_extraction(
        self,
        csv_zip,
        tmp_path,
        sample_rows: list[dict[str, object]],
    ) -> None:
        ParquetExtractorAdapterCVM().extract(
            source_path=str(csv_zip), destination_path=str(tmp_path)
        )

        table = pq.read_table(tmp_path / 'data.parquet')
        assert table.num_rows == len(sample_rows)
        assert table.column_names == ['id', 'name', 'value', 'category']
        assert table.to_pylist() == sample_rows

    def test_no_data_loss_with_special_characters(self, tmp_path) -> None:
        rows = [
            'name;city;description',
            'João;São Paulo;Ação da empresa',
            'José;Brasília;Título público',
            'María;Río;Índice',
            'François;Montréal;Câmbio',
            'Ñoño;España;Opção',
        ]
        zip_path = write_zip(
            tmp_path / 'special.zip',
            {'special.csv': csv_bytes(rows, encoding='latin-1')},
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        table = pq.read_table(tmp_path / 'special.parquet')
        assert table.num_rows == len(rows) - 1
        assert table.column_names == ['name', 'city', 'description']
        assert table.to_pylist() == [
            {
                'name': 'João',
                'city': 'São Paulo',
                'description': 'Ação da empresa',
            },
            {
                'name': 'José',
                'city': 'Brasília',
                'description': 'Título público',
            },
            {'name': 'María', 'city': 'Río', 'description': 'Índice'},
            {
                'name': 'François',
                'city': 'Montréal',
                'description': 'Câmbio',
            },
            {'name': 'Ñoño', 'city': 'España', 'description': 'Opção'},
        ]

    def test_no_data_loss_with_large_numbers(self, tmp_path) -> None:
        rows = [
            'big_int;float_precision;scientific',
            '9999999999999999;1.234567890123456;1.23e15',
            '1234567890123456;9.876543210987654;4.56e-10',
            '-9876543210987654;3.141592653589793;7.89e20',
        ]
        zip_path = write_zip(
            tmp_path / 'numeric.zip',
            {'numeric.csv': csv_bytes(rows, encoding='latin-1')},
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        result = pq.read_table(tmp_path / 'numeric.parquet').to_pylist()
        assert len(result) == len(rows) - 1
        assert [row['big_int'] for row in result] == [
            9999999999999999,
            1234567890123456,
            -9876543210987654,
        ]
        expected_float_values = [
            1.234567890123456,
            9.876543210987654,
            3.141592653589793,
        ]
        assert all(
            math.isclose(
                float(row['float_precision']),
                expected,
                rel_tol=1e-15,
                abs_tol=1e-15,
            )
            for row, expected in zip(
                result, expected_float_values, strict=True
            )
        )
        assert [row['scientific'] for row in result] == [
            1.23e15,
            4.56e-10,
            7.89e20,
        ]

    def test_zero_byte_csv_aborts_the_batch_without_partial_outputs(
        self, tmp_path
    ) -> None:
        zip_path = write_zip(
            tmp_path / 'mixed.zip',
            {
                'empty.csv': b'',
                'valid.csv': csv_bytes(
                    ['col1;col2', '1;a', '2;b'], encoding='latin-1'
                ),
            },
        )

        with pytest.raises(ExtractionError, match='CSV member has no header'):
            ParquetExtractorAdapterCVM().extract(
                source_path=str(zip_path), destination_path=str(tmp_path)
            )

        assert not (tmp_path / 'empty.parquet').exists()
        assert not (tmp_path / 'valid.parquet').exists()

    def test_header_only_csv_produces_valid_empty_parquet(
        self, tmp_path
    ) -> None:
        zip_path = write_zip(
            tmp_path / 'header_only.zip',
            {
                'empty.csv': csv_bytes(['col1;col2'], encoding='latin-1'),
                'valid.csv': csv_bytes(
                    ['col1;col2', '1;a', '2;b'], encoding='latin-1'
                ),
            },
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        assert (tmp_path / 'empty.parquet').exists()
        assert (tmp_path / 'valid.parquet').exists()
        metadata = pq.ParquetFile(tmp_path / 'empty.parquet').metadata
        assert metadata.num_rows == 0
        assert metadata.num_columns == 2

    def test_extracted_parquet_matches_csv_content(self, tmp_path) -> None:
        expected = [
            {
                'text': 'Ação',
                'int': 1,
                'float': 1.1,
                'date': '2023-01-01',
            },
            {
                'text': 'Fundo',
                'int': 2,
                'float': 2.2,
                'date': '2023-01-02',
            },
            {
                'text': 'Opção',
                'int': 3,
                'float': 3.3,
                'date': '2023-01-03',
            },
        ]
        rows = ['text;int;float;date']
        rows.extend(
            f'{row["text"]};{row["int"]};{row["float"]};{row["date"]}'
            for row in expected
        )
        csv_zip = write_zip(
            tmp_path / 'data.zip',
            {'data.csv': csv_bytes(rows, encoding='latin-1')},
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(csv_zip), destination_path=str(tmp_path)
        )

        assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == expected

    def test_handles_empty_values_correctly(self, tmp_path) -> None:
        zip_path = write_zip(
            tmp_path / 'empty_vals.zip',
            {'data.csv': csv_bytes(['a;b', '1;', ';2'])},
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        table = pq.read_table(tmp_path / 'data.parquet')
        assert table.num_rows == 2
        assert table.to_pylist() == [
            {'a': 1, 'b': None},
            {'a': None, 'b': 2},
        ]

    def test_handles_large_numbers_precision(self, tmp_path) -> None:
        large_num = 123456789.123456789
        zip_path = write_zip(
            tmp_path / 'precision.zip',
            {'data.csv': csv_bytes(['val', str(large_num)])},
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        value = pq.read_table(tmp_path / 'data.parquet').to_pylist()[0]['val']
        assert math.isclose(float(value), large_num, abs_tol=1e-7)

    def test_handles_latin1_encoding_correctly(self, tmp_path) -> None:
        special_text = 'Mãe, Ações, Vovô'
        zip_path = write_zip(
            tmp_path / 'encoding.zip',
            {
                'data.csv': csv_bytes(
                    ['text', special_text], encoding='latin-1'
                )
            },
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
            {'text': special_text}
        ]

    @pytest.mark.parametrize(
        ('encoding', 'bom'),
        [
            ('utf-8', False),
            ('utf-8', True),
            ('cp1252', False),
            ('latin-1', False),
        ],
    )
    def test_csv_encoding_round_trip_preserves_financial_text(
        self,
        tmp_path,
        encoding: str,
        bom: bool,
    ) -> None:
        """ZIP CSV text survives exact decoding and a Parquet round trip."""
        archive_path = write_zip(
            tmp_path / f'{encoding}-{bom}.zip',
            {
                'text.csv': csv_bytes(
                    [
                        'nome;acao;cidade',
                        'Mãe;Ação;São Paulo',
                        'José;Preferencial;Brasília',
                    ],
                    encoding=encoding,
                    bom=bom,
                )
            },
        )

        ParquetExtractorAdapterCVM().extract(
            source_path=str(archive_path), destination_path=str(tmp_path)
        )

        assert pq.read_table(tmp_path / 'text.parquet').to_pylist() == [
            {'nome': 'Mãe', 'acao': 'Ação', 'cidade': 'São Paulo'},
            {
                'nome': 'José',
                'acao': 'Preferencial',
                'cidade': 'Brasília',
            },
        ]

    def test_structurally_malformed_csv_aborts_without_silent_row_loss(
        self, tmp_path
    ) -> None:
        """A malformed member leaves no final output after its parser error."""
        archive_path = write_zip(
            tmp_path / 'malformed.zip',
            {
                'first.csv': csv_bytes(['id;name', '1;valid']),
                'second.csv': csv_bytes(
                    ['id;name', '2;valid', '3;malformed;extra_col;even_more']
                ),
            },
        )

        with pytest.raises(ExtractionError):
            ParquetExtractorAdapterCVM().extract(
                source_path=str(archive_path), destination_path=str(tmp_path)
            )

        assert not (tmp_path / 'first.parquet').exists()
        assert not (tmp_path / 'second.parquet').exists()
