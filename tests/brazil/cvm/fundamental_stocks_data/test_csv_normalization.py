"""Normalization spools are isolated and owned until conversion completes."""

import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    CvmCsvParquetPipeline,
    inference,
    source,
)

pytestmark = pytest.mark.integration


def _sources(tmp_path: Path) -> list[source.ReopenableCsvSource]:
    archive_path = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('first.csv', b'id;value\n1\n')
        archive.writestr('second.csv', b'id;value\n2\n')
    return [
        source.ReopenableCsvSource(archive_path, name)
        for name in ('first.csv', 'second.csv')
    ]


def test_simultaneous_normalizations_do_not_overwrite_each_other(
    tmp_path: Path,
) -> None:
    """Two active members keep separate complete spools in one staging area."""
    first, second = _sources(tmp_path)
    with (
        inference.normalize_short_rows(
            first,
            None,
            source.detect_encoding(first),
            tmp_path,
            ('id', 'value'),
        ) as first_path,
        inference.normalize_short_rows(
            second,
            None,
            source.detect_encoding(second),
            tmp_path,
            ('id', 'value'),
        ) as second_path,
    ):
        assert first_path != second_path
        assert first_path.read_bytes() == b'id;value\n1;\n'
        assert second_path.read_bytes() == b'id;value\n2;\n'
    assert not first_path.exists()
    assert not second_path.exists()


def test_conversion_failure_removes_its_normalization_spool(
    tmp_path: Path,
) -> None:
    """A caller failure cannot leave the conversion's normalized CSV behind."""
    first, _ = _sources(tmp_path)
    with (
        pytest.raises(ValueError, match='injected conversion failure'),
        inference.normalize_short_rows(
            first,
            None,
            source.detect_encoding(first),
            tmp_path,
            ('id', 'value'),
        ) as normalized,
    ):
        assert normalized.is_file()
        raise ValueError('injected conversion failure')
    assert not normalized.exists()
    assert first.source_path.is_file()


def test_pipeline_removes_normalization_spools_between_members(
    tmp_path: Path,
) -> None:
    """Each converted artifact survives after its temporary CSV is removed."""
    for index, csv_source in enumerate(_sources(tmp_path), start=1):
        output = tmp_path / f'{index}.parquet'
        CvmCsvParquetPipeline(
            csv_source.source_path, csv_source.member_name
        ).convert(staged_path=output, staging_dir=tmp_path)
        assert pq.read_table(output).to_pylist() == [
            {'id': str(index), 'value': ''}
        ]
        assert not list(tmp_path.glob('.cvm-normalized*.csv'))
