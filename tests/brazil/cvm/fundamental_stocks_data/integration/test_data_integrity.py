import zipfile

import pandas as pd
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import csv_bytes, write_zip


@pytest.mark.integration
class TestDataIntegrity:
    @pytest.fixture
    def sample_data(self):
        return pd.DataFrame(
            {
                'id': [1, 2, 3, 4, 5],
                'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
                'value': [10.5, 20.3, 30.7, 40.2, 50.9],
                'category': ['A', 'B', 'A', 'C', 'B'],
            }
        )

    @pytest.fixture
    def csv_zip(self, tmp_path, sample_data):
        zip_path = tmp_path / 'data.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            csv_content = sample_data.to_csv(sep=';', index=False)
            z.writestr('data.csv', csv_content.encode('latin-1'))
        return zip_path

    def test_no_data_loss_during_extraction(
        self, csv_zip, tmp_path, sample_data
    ):
        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(csv_zip), destination_path=str(tmp_path)
        )

        parquet_file = tmp_path / 'data.parquet'
        assert parquet_file.exists(), 'Parquet was not created'
        df_result = pd.read_parquet(parquet_file)
        assert len(df_result) == len(sample_data), (
            f'DATA LOSS! Original: {len(sample_data)} rows, '
            f'Result: {len(df_result)} rows'
        )
        assert list(df_result.columns) == list(sample_data.columns), (
            f'Different columns! Original: {list(sample_data.columns)}, '
            f'Result: {list(df_result.columns)}'
        )
        for col in sample_data.columns:
            assert df_result[col].equals(sample_data[col]), (
                f"DATA CORRUPTION in column '{col}'!"
            )

    def test_no_data_loss_with_special_characters(self, tmp_path):
        special_data = pd.DataFrame(
            {
                'name': ['João', 'José', 'María', 'François', 'Ñoño'],
                'city': ['São Paulo', 'Brasília', 'Río', 'Montréal', 'España'],
                'description': [
                    'Ação da empresa',
                    'Título público',
                    'Índice',
                    'Câmbio',
                    'Opção',
                ],
            }
        )
        zip_path = tmp_path / 'special.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            csv_content = special_data.to_csv(sep=';', index=False)
            z.writestr('special.csv', csv_content.encode('latin-1'))

        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        df_result = pd.read_parquet(tmp_path / 'special.parquet')
        for col in special_data.columns:
            for i, (original, result) in enumerate(
                zip(special_data[col], df_result[col], strict=False)
            ):
                assert original == result, (
                    f"Corrupted character at line {i}, column '{col}': "
                    f"'{original}' -> '{result}'"
                )

    def test_no_data_loss_with_large_numbers(self, tmp_path):
        numeric_data = pd.DataFrame(
            {
                'big_int': [
                    9999999999999999,
                    1234567890123456,
                    -9876543210987654,
                ],
                'float_precision': [
                    1.234567890123456,
                    9.876543210987654,
                    3.141592653589793,
                ],
                'scientific': [1.23e15, 4.56e-10, 7.89e20],
            }
        )
        zip_path = tmp_path / 'numeric.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            csv_content = numeric_data.to_csv(sep=';', index=False)
            z.writestr('numeric.csv', csv_content.encode('latin-1'))
        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        df_result = pd.read_parquet(tmp_path / 'numeric.parquet')
        for col in numeric_data.columns:
            if numeric_data[col].dtype == 'float64':
                assert (
                    numeric_data[col] - df_result[col]
                ).abs().max() < 1e-10, f"Loss of precision in column '{col}'"
            else:
                assert (numeric_data[col] == df_result[col]).all(), (
                    f"Integer corruption in column '{col}'"
                )

    def test_zero_byte_csv_aborts_the_batch_without_partial_outputs(
        self, tmp_path
    ):
        zip_path = tmp_path / 'mixed.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('empty.csv', b'')
            valid_data = pd.DataFrame({'col1': [1, 2], 'col2': ['a', 'b']})
            csv_content = valid_data.to_csv(sep=';', index=False)
            z.writestr('valid.csv', csv_content.encode('latin-1'))
        extractor = ParquetExtractorAdapterCVM()
        with pytest.raises(ExtractionError, match='CSV member has no header'):
            extractor.extract(
                source_path=str(zip_path), destination_path=str(tmp_path)
            )

        assert not (tmp_path / 'empty.parquet').exists()
        assert not (tmp_path / 'valid.parquet').exists()

    def test_header_only_csv_produces_valid_empty_parquet(self, tmp_path):
        zip_path = tmp_path / 'header_only.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('empty.csv', b'col1;col2\n')
            valid_data = pd.DataFrame({'col1': [1, 2], 'col2': ['a', 'b']})
            csv_content = valid_data.to_csv(sep=';', index=False)
            z.writestr('valid.csv', csv_content.encode('latin-1'))
        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        assert (tmp_path / 'empty.parquet').exists()
        assert (tmp_path / 'valid.parquet').exists()
        meta = pq.ParquetFile(tmp_path / 'empty.parquet').metadata
        assert meta.num_rows == 0
        assert meta.num_columns == 2

    def test_extracted_parquet_matches_csv_content(self, tmp_path):
        df_original = pd.DataFrame(
            {
                'text': ['Ação', 'Fundo', 'Opção'],
                'int': [1, 2, 3],
                'float': [1.1, 2.2, 3.3],
                'date': ['2023-01-01', '2023-01-02', '2023-01-03'],
            }
        )

        csv_zip = tmp_path / 'data.zip'
        with zipfile.ZipFile(csv_zip, 'w') as z:
            z.writestr(
                'data.csv',
                df_original.to_csv(sep=';', index=False).encode('latin-1'),
            )

        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(csv_zip), destination_path=str(tmp_path)
        )

        parquet_file = tmp_path / 'data.parquet'
        assert parquet_file.exists()

        df_parquet = pd.read_parquet(parquet_file)

        pd.testing.assert_frame_equal(
            df_parquet.sort_index(axis=1),
            df_original.sort_index(axis=1),
            check_dtype=False,
        )

    def test_handles_empty_values_correctly(self, tmp_path):
        zip_path = tmp_path / 'empty_vals.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('data.csv', 'a;b\n1;\n;2')

        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        df = pd.read_parquet(tmp_path / 'data.parquet')
        assert pd.isna(df.iloc[0, 1]) or df.iloc[0, 1] == ''
        assert pd.isna(df.iloc[1, 0]) or df.iloc[1, 0] == ''

    def test_handles_large_numbers_precision(self, tmp_path):
        zip_path = tmp_path / 'precision.zip'
        large_num = 123456789.123456789
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('data.csv', f'val\n{large_num}')

        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        df = pd.read_parquet(tmp_path / 'data.parquet')
        assert abs(float(df.iloc[0, 0]) - large_num) < 1e-7

    def test_handles_latin1_encoding_correctly(self, tmp_path):
        zip_path = tmp_path / 'encoding.zip'
        special_text = 'Mãe, Ações, Vovô'
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('data.csv', f'text\n{special_text}'.encode('latin-1'))

        extractor = ParquetExtractorAdapterCVM()
        extractor.extract(
            source_path=str(zip_path), destination_path=str(tmp_path)
        )

        df = pd.read_parquet(tmp_path / 'data.parquet')
        assert df.iloc[0, 0] == special_text

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
    ):
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

        frame = pd.read_parquet(tmp_path / 'text.parquet')
        assert list(frame.columns) == ['nome', 'acao', 'cidade']
        assert frame.to_dict('records') == [
            {'nome': 'Mãe', 'acao': 'Ação', 'cidade': 'São Paulo'},
            {
                'nome': 'José',
                'acao': 'Preferencial',
                'cidade': 'Brasília',
            },
        ]

    def test_structurally_malformed_csv_aborts_without_silent_row_loss(
        self, tmp_path
    ):
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
