"""Public writer resources close before rollback and atomic publication."""

from __future__ import annotations

import errno
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    B3ParquetWriterSession,
    ParquetWriterB3,
    build_b3_schema,
)
from globaldatafinance.macro_exceptions import (
    DiskFullError,
    ExtractionError,
    ParquetWriteError,
)
from tests.support.builders import build_b3_typed_record

pytestmark = pytest.mark.integration


@pytest.fixture
def arrow_handles(monkeypatch: pytest.MonkeyPatch) -> tuple[list, list]:
    """Retain real handles so collection cannot conceal missing closes."""
    writers: list = []
    readers: list = []
    original_open = B3ParquetWriterSession.open
    original_reader = pq.ParquetFile

    def observe_open(self, *args, **kwargs):
        session = original_open(self, *args, **kwargs)
        writers.append((session, session._writer))
        return session

    def observe_reader(*args, **kwargs):
        reader = original_reader(*args, **kwargs)
        readers.append(reader)
        return reader

    monkeypatch.setattr(B3ParquetWriterSession, 'open', observe_open)
    monkeypatch.setattr(pq, 'ParquetFile', observe_reader)
    return writers, readers


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['overwrite', 'append'])
async def test_invalid_records_close_writer_before_removing_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arrow_handles: tuple[list, list],
    mode: str,
) -> None:
    """A conversion error keeps the old file and releases every open handle."""
    output = tmp_path / 'quotes.parquet'
    writer = ParquetWriterB3()
    await writer.write_to_parquet([build_b3_typed_record()], output)
    before = output.read_bytes()
    writers, readers = arrow_handles
    original_unlink = Path.unlink
    unlink_states = []

    def observe_unlink(path, *args, **kwargs):
        if path.name.endswith('.parquet.tmp'):
            unlink_states.append(writers[-1][0].state)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', observe_unlink)
    invalid = build_b3_typed_record()
    del invalid['ticker']

    with pytest.raises(KeyError) as raised:
        await writer.write_to_parquet([invalid], output, mode=mode)

    assert raised.value.args == ('ticker',)
    assert len(writers) == 2
    assert all(session.state == 'CLOSED' for session, _handle in writers)
    assert all(not handle.is_open for _session, handle in writers)
    assert readers and all(reader.closed for reader in readers)
    assert unlink_states == ['CLOSED']
    assert output.read_bytes() == before
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['overwrite', 'append'])
async def test_success_closes_all_handles_before_atomic_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arrow_handles: tuple[list, list],
    mode: str,
) -> None:
    """Append and overwrite release their readers before replacing output."""
    output = tmp_path / 'quotes.parquet'
    writer = ParquetWriterB3()
    await writer.write_to_parquet(
        [build_b3_typed_record(ticker='PETR4')], output
    )
    writers, readers = arrow_handles
    original_replace = Path.replace
    publication_states = []

    def observe_replace(path, target):
        publication_states.append(
            (
                all(not handle.is_open for _session, handle in writers),
                all(reader.closed for reader in readers),
            )
        )
        return original_replace(path, target)

    monkeypatch.setattr(Path, 'replace', observe_replace)

    await writer.write_to_parquet(
        [build_b3_typed_record(ticker='VALE3')], output, mode=mode
    )

    assert len(writers) == 2
    assert all(session.state == 'CLOSED' for session, _handle in writers)
    assert publication_states == [(True, True)]
    assert len(readers) == (3 if mode == 'append' else 2)
    assert pq.read_table(output)['ticker'].to_pylist() == (
        ['PETR4', 'VALE3'] if mode == 'append' else ['VALE3']
    )
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.asyncio
async def test_append_schema_failure_closes_existing_reader_and_writer(
    tmp_path: Path, arrow_handles: tuple[list, list]
) -> None:
    """Schema rejection closes the old input and discards the new artifact."""
    output = tmp_path / 'quotes.parquet'
    pq.write_table(pa.table({'wrong': [1]}), output)
    before = output.read_bytes()

    with pytest.raises(ParquetWriteError, match='schema is incompatible'):
        await ParquetWriterB3().write_to_parquet(
            [build_b3_typed_record()], output, mode='append'
        )

    writers, readers = arrow_handles
    assert len(writers) == 1
    assert writers[0][0].state == 'CLOSED'
    assert writers[0][1].is_open is False
    assert readers and all(reader.closed for reader in readers)
    assert output.read_bytes() == before
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.asyncio
async def test_primary_conversion_error_survives_cleanup_flush_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arrow_handles: tuple[list, list],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cleanup failure is diagnosed without replacing the record exception."""
    output = tmp_path / 'quotes.parquet'
    output.write_bytes(b'previous output')
    failure = OSError(errno.EIO, 'injected cleanup flush failure')

    def fail_flush(_self):
        raise failure

    monkeypatch.setattr(B3ParquetWriterSession, 'flush_row_group', fail_flush)
    invalid = build_b3_typed_record()
    del invalid['ticker']

    with pytest.raises(KeyError) as raised:
        await ParquetWriterB3().write_to_parquet([invalid], output)

    writers, _readers = arrow_handles
    assert raised.value.args == ('ticker',)
    assert writers[0][0].state == 'CLOSED'
    assert writers[0][1].is_open is False
    assert any(
        record.exc_info and record.exc_info[1] is failure
        for record in caplog.records
    )
    assert output.read_bytes() == b'previous output'
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('error_number', 'message', 'expected_error'),
    [
        (errno.EACCES, 'injected replace failure', ParquetWriteError),
        (errno.ENOSPC, 'injected disk full failure', DiskFullError),
        (errno.EIO, 'No space left on device', DiskFullError),
    ],
    ids=['io', 'disk-full-errno', 'disk-full-message'],
)
async def test_publication_failure_closes_all_handles_and_keeps_original_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arrow_handles: tuple[list, list],
    error_number: int,
    message: str,
    expected_error: type[Exception],
) -> None:
    """A failed atomic replace preserves the old bytes and the I/O cause."""
    output = tmp_path / 'quotes.parquet'
    output.write_bytes(b'previous output')
    failure = OSError(error_number, message)

    def fail_replace(_path, _target):
        raise failure

    monkeypatch.setattr(Path, 'replace', fail_replace)

    with pytest.raises(expected_error) as raised:
        await ParquetWriterB3().write_to_parquet(
            [build_b3_typed_record()], output
        )

    writers, readers = arrow_handles
    assert raised.value.__cause__ is failure
    assert writers[0][0].state == 'CLOSED'
    assert writers[0][1].is_open is False
    assert readers and all(reader.closed for reader in readers)
    assert output.read_bytes() == b'previous output'
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.asyncio
async def test_unlink_failure_logs_cause_without_replacing_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arrow_handles: tuple[list, list],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unlink failure is logged while the primary error remains intact."""
    output = tmp_path / 'quotes.parquet'
    output.write_bytes(b'previous output')
    failure = PermissionError(errno.EACCES, 'injected unlink failure')
    original_unlink = Path.unlink
    blocked_paths = []

    def fail_temporary_unlink(path, *args, **kwargs):
        if path.name.endswith('.parquet.tmp'):
            blocked_paths.append(path)
            raise failure
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', fail_temporary_unlink)
    invalid = build_b3_typed_record()
    del invalid['ticker']

    with pytest.raises(KeyError) as raised:
        await ParquetWriterB3().write_to_parquet([invalid], output)

    writers, readers = arrow_handles
    assert raised.value.args == ('ticker',)
    assert len(writers) == 1
    assert writers[0][0].state == 'CLOSED'
    assert writers[0][1].is_open is False
    assert readers and all(reader.closed for reader in readers)
    assert any(
        record.getMessage() == 'B3 Parquet temporary cleanup failed'
        and record.exc_info
        and record.exc_info[1] is failure
        for record in caplog.records
    )
    assert output.read_bytes() == b'previous output'
    assert len(blocked_paths) == 1
    assert blocked_paths[0].is_file()
    assert set(tmp_path.iterdir()) == {output, blocked_paths[0]}
    original_unlink(blocked_paths[0])
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize('failure', ['none', 'rows', 'schema'])
def test_session_validation_always_closes_its_parquet_reader(
    tmp_path: Path, arrow_handles: tuple[list, list], failure: str
) -> None:
    """Both valid and rejected readback artifacts release the real reader."""
    output = tmp_path / 'quotes.parquet'
    session = B3ParquetWriterSession().open(output, build_b3_schema())
    session.close()
    if failure == 'rows':
        session.rows_written = 1
    elif failure == 'schema':
        session.schema = pa.schema([('wrong', pa.int64())])

    if failure == 'none':
        session.validate()
    else:
        with pytest.raises(ExtractionError, match='validation failed'):
            session.validate()

    _writers, readers = arrow_handles
    assert len(readers) == 2
    assert all(reader.closed for reader in readers)
