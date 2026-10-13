"""Storage, encoding, and schema failures preserve CVM source evidence."""

from __future__ import annotations

import codecs
import errno
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    inference,
    source,
    writer,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import (
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)

pytestmark = pytest.mark.integration


def _csv_source(root: Path, contents: bytes):
    """Create a real bounded archive and its reopenable CSV source."""
    path = root / 'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', contents)
    return source.ReopenableCsvSource(path, 'data.csv')


@pytest.mark.parametrize(
    ('contents', 'message'),
    [(b' \n1\n', 'usable header'), (b'a;a\n1;2\n', 'duplicate header')],
)
def test_invalid_headers_never_replace_existing_output(
    tmp_path: Path, contents: bytes, message: str
) -> None:
    """Ambiguous column identity fails before any publication."""
    csv_source = _csv_source(tmp_path, contents)
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    with pytest.raises(ExtractionError, match=message):
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    assert previous.read_bytes() == b'previous output'


def test_column_count_is_bounded_before_output(tmp_path: Path) -> None:
    """Extremely wide input cannot allocate unbounded column buffers."""
    csv_source = _csv_source(
        tmp_path,
        (';'.join(f'c{index}' for index in range(4097)) + '\n').encode(),
    )
    with pytest.raises(ExtractionError, match='4096 columns'):
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    assert not (tmp_path / 'data.parquet').exists()


def test_excessive_data_width_is_rejected_with_a_global_column_bound(
    tmp_path: Path,
) -> None:
    """A separator-heavy data row is bounded before allocating its fields."""
    csv_source = _csv_source(tmp_path, b'value\n' + b';' * 200_000 + b'\n')
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    with pytest.raises(ExtractionError, match='4096 columns'):
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    assert previous.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.parametrize('error_number', [errno.ENOSPC, errno.EIO])
@pytest.mark.parametrize('contents', [b'a;b\n1\n', b'value\n\x80\n'])
def test_spool_write_failures_keep_input_and_previous_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    contents: bytes,
) -> None:
    """Normalization and encoding spools fail without a partial cutover."""
    csv_source = _csv_source(tmp_path, contents)
    original_bytes = csv_source.source_path.read_bytes()
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    original_open = Path.open
    failure = OSError(error_number, 'injected spool storage failure')

    def fail_spool(path, *args, **kwargs):
        if path.name.startswith('.cvm-') and path.name.endswith('.csv'):
            raise failure
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', fail_spool)
    expected = (
        DiskFullError if error_number == errno.ENOSPC else ExtractionError
    )
    with pytest.raises(expected) as captured:
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    assert captured.value.__cause__ is failure
    assert csv_source.source_path.read_bytes() == original_bytes
    assert previous.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


def test_changed_header_is_rejected_during_short_row_normalization(
    tmp_path: Path,
) -> None:
    """A normalization pass cannot reuse a different source's column plan."""
    csv_source = _csv_source(tmp_path, b'changed;header\n1\n')
    plan = source.detect_encoding(csv_source)
    with pytest.raises(ExtractionError, match='header changed'):
        inference.normalize_short_rows(
            csv_source, None, plan, tmp_path, ('original', 'header')
        )
    assert csv_source.source_path.exists()


def test_missing_bom_invalidates_a_previously_observed_encoding_plan(
    tmp_path: Path,
) -> None:
    """A reopened source cannot silently change its encoding prefix."""
    csv_source = _csv_source(tmp_path, codecs.BOM_UTF8 + b'value\n1\n')
    plan = source.detect_encoding(csv_source)
    _csv_source(tmp_path, b'value\n1\n')
    with (
        pytest.raises(ExtractionError, match='BOM disappeared'),
        source.text_source(csv_source, None, plan) as text,
    ):
        text.read()


@pytest.mark.parametrize(
    'contents', [b'value\n\xe2', b'value\n\xff' + b'x' * (128 * 1024)]
)
def test_incomplete_and_early_invalid_utf8_are_detected_over_complete_input(
    tmp_path: Path, contents: bytes
) -> None:
    """The codec scan validates EOF and continues across invalid blocks."""
    plan = source.detect_encoding(_csv_source(tmp_path, contents))
    assert plan.encoding != 'utf-8'
    assert plan.needs_utf8_spool is True


def test_bad_zip_is_preserved_as_a_cause_when_a_member_is_reopened(
    tmp_path: Path,
) -> None:
    """The source reader preserves archive failure context."""
    path = tmp_path / 'source.zip'
    path.write_bytes(b'not an archive')
    csv_source = source.ReopenableCsvSource(path, 'data.csv')
    with pytest.raises(ExtractionError, match='Could not reopen') as captured:
        source.detect_encoding(csv_source)
    assert isinstance(captured.value.__cause__, zipfile.BadZipFile)


@pytest.mark.parametrize('mismatch', ['schema', 'rows', 'groups', 'pandas'])
def test_staged_parquet_metadata_cannot_disagree_with_its_plan(
    tmp_path: Path, mismatch: str
) -> None:
    """Real Parquet metadata is checked against every publication invariant."""
    csv_source = _csv_source(tmp_path, b'value\n1\n')
    actual = pa.schema(
        [('value', pa.string())],
        metadata={b'pandas': b'{}'} if mismatch == 'pandas' else None,
    )
    path = tmp_path / 'staged.parquet'
    pq.write_table(pa.Table.from_pylist([{'value': '1'}], schema=actual), path)
    expected = (
        pa.schema([('other', pa.string())]) if mismatch == 'schema' else actual
    )
    with pq.ParquetFile(path) as parquet, pytest.raises(ExtractionError):
        writer._validate_parquet_metadata(
            csv_source,
            parquet,
            expected,
            2 if mismatch == 'rows' else 1,
            [2] if mismatch == 'groups' else [1],
        )


@pytest.mark.parametrize('error_number', [errno.ENOSPC, errno.EIO])
def test_staging_directory_write_failures_remain_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """A staging allocation failure cannot produce a success artifact."""
    csv_source = _csv_source(tmp_path, b'value\n1\n')
    plan = source.detect_encoding(csv_source)
    analysis = inference.analyse_csv(csv_source, None, plan)
    schema = inference.build_schema(analysis)
    failure = OSError(error_number, 'injected staging allocation failure')

    def fail_mkdir(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(Path, 'mkdir', fail_mkdir)
    expected = (
        DiskFullError if error_number == errno.ENOSPC else ParquetWriteError
    )
    with pytest.raises(expected) as captured:
        writer.write_parquet(
            csv_source,
            None,
            plan,
            tmp_path / 'staged.parquet',
            analysis,
            schema,
        )
    assert captured.value.__cause__ is failure
    assert not (tmp_path / 'staged.parquet').exists()


@pytest.mark.parametrize('failure_kind', ['arrow', 'storage', 'truncated'])
def test_csv_engine_failures_preserve_the_previous_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_kind: str
) -> None:
    """A dependency failure or dropped record cannot publish partial data."""
    csv_source = _csv_source(tmp_path, b'value\noriginal\nsecond\n')
    original_bytes = csv_source.source_path.read_bytes()
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    failure = (
        pa.ArrowInvalid('CSV engine rejected input')
        if failure_kind == 'arrow'
        else OSError(errno.EIO, 'CSV engine input read failed')
    )

    def failing_reader(*_args, **_kwargs):
        if failure_kind == 'truncated':
            return iter([pa.record_batch({'value': ['original']})])
        raise failure

    monkeypatch.setattr(pacsv, 'open_csv', failing_reader)
    with pytest.raises(ExtractionError) as captured:
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    if failure_kind == 'truncated':
        assert 'expected 2, wrote 1' in str(captured.value)
    else:
        assert captured.value.__cause__ is failure
    assert previous.read_bytes() == b'previous output'
    assert csv_source.source_path.read_bytes() == original_bytes
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.parametrize('error_number', [errno.EIO, errno.ENOSPC])
def test_parquet_engine_write_failure_retains_its_storage_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """Disk errors close the writer and discard the staged output."""
    csv_source = _csv_source(tmp_path, b'value\noriginal\n')
    previous = tmp_path / 'data.parquet'
    previous.write_bytes(b'previous output')
    original_writer = pq.ParquetWriter
    failure = OSError(error_number, 'Parquet engine disk write failed')
    closed: list[bool] = []

    class FailingWriter:
        def __init__(self, *args, **kwargs):
            self.writer = original_writer(*args, **kwargs)

        def write_table(self, *_args, **_kwargs):
            raise failure

        def close(self):
            self.writer.close()
            closed.append(True)

    monkeypatch.setattr(pq, 'ParquetWriter', FailingWriter)
    expected = (
        DiskFullError if error_number == errno.ENOSPC else ParquetWriteError
    )
    with pytest.raises(expected) as captured:
        ParquetExtractorAdapterCVM().extract(
            str(csv_source.source_path), str(tmp_path)
        )
    assert captured.value.__cause__ is failure
    assert closed == [True]
    assert previous.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))
