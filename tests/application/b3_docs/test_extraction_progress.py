"""Integration tests for visible progress in the public B3 extraction flow."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('processing_mode', ['fast', 'slow'])
@pytest.mark.parametrize('source_format', ['txt', 'zip'])
@pytest.mark.parametrize('verbose', [False, True])
def test_public_extraction_reports_both_file_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    processing_mode: str,
    source_format: str,
    verbose: bool,
) -> None:
    """Both modes report file counts independently of final verbosity."""
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'thread')
    source = tmp_path / 'source'
    source.mkdir()
    write_source = (
        write_cotahist_txt if source_format == 'txt' else write_cotahist_zip
    )
    for year in (2023, 2024):
        write_source(
            source,
            year=year,
            records=[build_cotahist_record(year=year)],
        )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(source),
        initial_year=2023,
        last_year=2024,
        destination_path=str(tmp_path / 'output'),
        processing_mode=processing_mode,
        verbose=verbose,
    )

    output = capsys.readouterr().out
    validation, processing = output.split('Processing B3 files:', maxsplit=1)
    assert 'Validating B3 files:' in validation
    for phase in (validation, processing):
        assert '0/2 (0%)' in phase
        assert '2/2 (100%)' in phase
        assert '░' in phase
        assert '█' in phase
    assert ('B3 Historical Quotes Extraction' in output) is verbose
    if verbose:
        assert output.index('Processing B3 files:') < output.index(
            'B3 Historical Quotes Extraction'
        )
    assert output.endswith('\n')
    assert result['success'] is True
    assert result['success_count'] == 2
    assert result['total_records'] == 2
    assert pq.ParquetFile(result['output_file']).metadata.num_rows == 2


def test_invalid_source_closes_validation_progress_before_extraction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad second year preserves validation counts and publishes nothing."""
    source = tmp_path / 'source'
    source.mkdir()
    write_cotahist_txt(
        source,
        year=2023,
        records=[build_cotahist_record(year=2023)],
    )
    (source / 'COTAHIST_A2024.TXT').write_bytes(b'invalid record\n')
    destination = tmp_path / 'output'

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(source),
        initial_year=2023,
        last_year=2024,
        destination_path=str(destination),
        verbose=False,
    )

    output = capsys.readouterr().out
    assert 'Validating B3 files:' in output
    assert '1/2 (50%)' in output
    assert '(100%)' not in output
    assert 'Processing B3 files' not in output
    assert output.endswith('\n')
    assert result['success'] is False
    assert result['output_file'] == ''
    assert not destination.exists()


def test_missing_sources_do_not_display_completed_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing annual selection cannot produce a completed progress bar."""
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2023,
        last_year=2023,
        verbose=False,
    )

    assert capsys.readouterr().out == ''
    assert result['success'] is False
    assert result['integrity']['missing_years'] == [2023]
