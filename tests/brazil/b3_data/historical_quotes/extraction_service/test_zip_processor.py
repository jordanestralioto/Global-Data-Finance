"""B3 source-worker tests for strict bounded Arrow artifacts."""

import hashlib
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    cotahist_parser,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def test_processor_writes_one_validated_temp_artifact_per_source(
    tmp_path: Path,
) -> None:
    """The worker holds no more than the configured Python record buffer."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(ticker='PETR4'),
            build_cotahist_record(ticker='VALE3'),
        ],
    )
    output = tmp_path / 'staging' / 'source.parquet'
    processor = extraction_service.ZipProcessorB3(
        ZipFileReaderB3(), python_record_limit=1
    )

    result = processor.process(source, {'010'}, output)

    assert result.temp_path == output
    assert result.selected_records == 2
    assert result.parsed_records == result.written_records == 2
    assert pq.ParquetFile(output).read()['ticker'].to_pylist() == [
        'PETR4',
        'VALE3',
    ]


def test_processor_returns_no_temp_artifact_when_every_record_is_filtered(
    tmp_path: Path,
) -> None:
    """Valid but nonmatching records remain a successful zero-row source."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(market='070')],
    )
    output = tmp_path / 'staging' / 'filtered.parquet'

    result = extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
        source, {'010'}, output
    )

    assert result.temp_path is None
    assert result.metrics.filtered_records == 1
    assert result.written_records == 0
    assert output.exists() is False


def test_processor_removes_derived_temp_on_selected_record_failure(
    tmp_path: Path,
) -> None:
    """A malformed financial record cannot leave a publishable temp behind."""
    malformed = build_cotahist_record()[:244]
    source = write_cotahist_txt(tmp_path, year=2024, records=[malformed])
    output = tmp_path / 'staging' / 'broken.parquet'

    with pytest.raises(ExtractionError, match='Expected exactly 245'):
        extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
            source, {'010'}, output
        )

    assert output.exists() is False
    assert source.exists()


def test_parser_subclass_preserves_all_markets_and_source_evidence(
    tmp_path: Path,
) -> None:
    """A parser subclass cannot drop markets or bypass source provenance."""

    class SourceParser(CotahistParserB3):
        """Use the same canonical parser through a caller-owned factory."""

    records = [
        build_cotahist_record(market=market)
        for market in ('010', '021', '999')
    ]
    source = write_cotahist_txt(tmp_path, year=2024, records=records)
    output = tmp_path / 'staging' / 'all.parquet'
    result = extraction_service.ZipProcessorB3(
        ZipFileReaderB3(), parser_factory=SourceParser, python_record_limit=1
    ).process(source, set(), output, all_markets=True)

    table = pq.read_table(output)
    assert result.written_records == result.selected_records == 3
    assert result.parsed_rows_sha256 == result.expected_rows_sha256
    assert table['tipo_mercado'].to_pylist() == ['010', '021', '999']
    assert table['registro_original'].to_pylist() == [
        record.encode('latin-1') for record in records
    ]
    assert table['ano_origem'].to_pylist() == [2024] * 3
    assert table['linha_origem'].to_pylist() == [2, 3, 4]
    assert (
        table['id_fonte'].to_pylist()
        == [hashlib.sha256(source.read_bytes()).hexdigest()] * 3
    )


def test_parser_subclass_cannot_publish_a_modified_financial_value(
    tmp_path: Path,
) -> None:
    """An extension's changed price fails the actual source replay digest."""

    class AdjustedParser(CotahistParserB3):
        """Change one valid price after canonical conversion."""

        def _select_quote(
            self,
            values: cotahist_parser.CsvRow,
            market: str,
            target_tpmerc_codes: set[str],
            all_markets: bool,
        ) -> cotahist_parser.CsvRow | None:
            row = super()._select_quote(
                values, market, target_tpmerc_codes, all_markets
            )
            return None if row is None else (*row[:6], '0.01', *row[7:])

    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    output = tmp_path / 'staging' / 'modified.parquet'
    processor = extraction_service.ZipProcessorB3(
        ZipFileReaderB3(), parser_factory=AdjustedParser
    )

    with pytest.raises(ExtractionError, match='selected-row digest changed'):
        processor.process(source, {'010'}, output)

    assert not output.exists()
    assert source.exists()
