"""Source changes and obsolete artifacts cannot produce false success."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import transaction
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import ExtractionError

pytestmark = pytest.mark.integration


def _archive(path: Path, members: dict[str, bytes]) -> None:
    """Write an actual ZIP for each source revision."""
    with zipfile.ZipFile(path, 'w') as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)


def test_replaced_source_cannot_publish_mislabeled_archive_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pathname replacement during conversion preserves previous outputs."""
    source = tmp_path / 'source.zip'
    replacement = tmp_path / 'replacement.zip'
    _archive(source, {'data.csv': b'value\noriginal\n'})
    _archive(replacement, {'data.csv': b'value\nreplacement\n'})
    output = tmp_path / 'data.parquet'
    output.write_bytes(b'previous output')
    original_convert = transaction.CvmCsvParquetPipeline.convert

    def replace_then_convert(pipeline, **kwargs):
        replacement.replace(source)
        return original_convert(pipeline, **kwargs)

    monkeypatch.setattr(
        transaction.CvmCsvParquetPipeline, 'convert', replace_then_convert
    )
    with pytest.raises(ExtractionError, match='source changed'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))
    assert output.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.parametrize('revision', ['removed', 'renamed'])
def test_source_revision_cannot_leave_obsolete_parquets_as_success(
    tmp_path: Path, revision: str
) -> None:
    """Removed members require a clean destination before regeneration."""
    source = tmp_path / 'source.zip'
    _archive(
        source,
        {'kept.csv': b'value\noriginal\n', 'removed.csv': b'value\nold\n'},
    )
    extractor = ParquetExtractorAdapterCVM()
    extractor.extract(str(source), str(tmp_path))
    previous = {path: path.read_bytes() for path in tmp_path.glob('*.parquet')}
    revised = {'kept.csv': b'value\nupdated\n'}
    if revision == 'renamed':
        revised['renamed.csv'] = b'value\nnew\n'
    _archive(source, revised)

    with pytest.raises(ExtractionError, match='Obsolete CVM artifacts'):
        extractor.extract(str(source), str(tmp_path))
    assert {path: path.read_bytes() for path in previous} == previous
    assert not (tmp_path / 'renamed.parquet').exists()


def test_independent_archive_artifacts_remain_valid_in_shared_directory(
    tmp_path: Path,
) -> None:
    """Inventory ownership distinguishes unrelated archives and years."""
    extractor = ParquetExtractorAdapterCVM()
    first = tmp_path / 'first.zip'
    second = tmp_path / 'second.zip'
    _archive(first, {'first.csv': b'value\nfirst\n'})
    _archive(second, {'second.csv': b'value\nsecond\n'})
    extractor.extract(str(first), str(tmp_path))
    extractor.extract(str(second), str(tmp_path))
    assert pq.read_table(tmp_path / 'first.parquet').to_pylist() == [
        {'value': 'first'}
    ]
    assert pq.read_table(tmp_path / 'second.parquet').to_pylist() == [
        {'value': 'second'}
    ]


def test_official_source_rejects_obsolete_legacy_artifacts(
    tmp_path: Path,
) -> None:
    """Official document/year names identify old files without new metadata."""
    source = tmp_path / 'dfp_cia_aberta_2024.zip'
    _archive(source, {'dfp_cia_aberta_2024.csv': b'value\nnew\n'})
    previous = tmp_path / 'dfp_cia_aberta_removed_2024.parquet'
    previous.write_bytes(b'legacy output')
    with pytest.raises(ExtractionError, match='Obsolete CVM artifacts'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))
    assert previous.read_bytes() == b'legacy output'
    assert not (tmp_path / 'dfp_cia_aberta_2024.parquet').exists()
