"""Protect responsiveness and publication across blocking async phases."""

import asyncio
import threading
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.application.b3_docs.historical_quotes import (
    extraction_flow,
)
from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    FileOperations,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _phase_boundary(phase):
    if phase == 'acquisition':
        return extraction_service.service.publication, 'begin_publication'
    if phase == 'rollback':
        return (
            extraction_service.service.orchestrator,
            'abort_after_cancellation',
        )
    if phase == 'preflight':
        return extraction_flow.ExtractionFlowB3, '_prepare_extraction'
    if phase == 'readback':
        return extraction_service.service.publication, 'verify_b3_parquet'
    return extraction_service.service.orchestrator, {
        'private': 'verify_private_sources',
        'merge': 'merge_and_verify_output',
        'checksum': 'verify_source_files',
    }[phase]


def _is_selected_call(phase, kwargs):
    return phase != 'readback' or 'manifest_sources' not in kwargs


@pytest.mark.parametrize('phase', ['preflight', 'readback'])
async def test_actual_heavy_phases_allow_async_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """A heartbeat progresses while real preparation or readback runs."""
    write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record()] * 5_000,
    )
    active = threading.Event()
    stopped = asyncio.Event()
    ticks = []
    phase_threads = []
    target, name = _phase_boundary(phase)
    operation = getattr(target, name)

    def observe_phase(*args, **kwargs):
        if not _is_selected_call(phase, kwargs):
            return operation(*args, **kwargs)
        phase_threads.append(threading.get_ident())
        active.set()
        try:
            return operation(*args, **kwargs)
        finally:
            active.clear()

    async def heartbeat():
        while not stopped.is_set():
            await asyncio.sleep(0.001)
            if active.is_set():
                ticks.append(True)

    monkeypatch.setattr(target, name, observe_phase)
    pulse = asyncio.create_task(heartbeat())
    try:
        result = await HistoricalQuotesB3().extract_async(
            path_of_docs=str(tmp_path),
            initial_year=2024,
            last_year=2024,
            destination_path=str(tmp_path / 'output'),
            verbose=False,
        )
    finally:
        stopped.set()
        await pulse

    assert result['success'] is True
    assert result['total_records'] == 5_000
    assert ticks
    assert phase_threads and all(
        ident != threading.get_ident() for ident in phase_threads
    )


@pytest.mark.parametrize(
    'phase',
    ['preflight', 'acquisition', 'private', 'merge', 'readback', 'checksum'],
)
async def test_cancellation_in_heavy_phase_joins_work_and_preserves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """Cancellation is delivered before commit and cleanup follows joins."""
    sources = tmp_path / 'sources'
    sources.mkdir()
    for year in (2023, 2024):
        write_cotahist_txt(
            sources,
            year=year,
            records=[build_cotahist_record(year=year)] * 256,
        )
    destination = tmp_path / 'output'
    destination.mkdir()
    output = destination / 'quotes.parquet'
    pq.write_table(pa.table({'previous': [1]}), output)
    previous = output.read_bytes()
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()
    target, name = _phase_boundary(phase)
    operation = getattr(target, name)

    def request_cancel_during_actual_phase(*args, **kwargs):
        if not _is_selected_call(phase, kwargs):
            return operation(*args, **kwargs)
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(timeout=5)
            return operation(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(target, name, request_cancel_during_actual_phase)
    task = asyncio.create_task(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(sources),
            initial_year=2023,
            last_year=2024,
            destination_path=str(destination),
            output_filename=output.name,
            verbose=False,
        )
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not finished.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    assert finished.is_set()
    assert output.read_bytes() == previous
    assert sorted(path.name for path in destination.iterdir()) == [output.name]
    assert not any(
        thread.name.startswith('gdf-b3-phase')
        for thread in threading.enumerate()
    )


async def test_repeated_cancel_during_rollback_waits_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback joins off-loop before the original cancellation escapes."""
    write_cotahist_txt(tmp_path, year=2024, records=[build_cotahist_record()])
    destination = tmp_path / 'output'
    destination.mkdir()
    output = destination / 'quotes.parquet'
    output.write_bytes(b'previous output')
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    aborted = threading.Event()
    target, name = _phase_boundary('rollback')
    abort = getattr(target, name)

    def hold_rollback(publication):
        if publication is None:
            return abort(publication)
        assert threading.get_ident() != loop_thread
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=5)
        try:
            return abort(publication)
        finally:
            aborted.set()

    async def cancel_sources(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(target, name, hold_rollback)
    monkeypatch.setattr(
        extraction_service.service.orchestrator.ExtractionServiceB3,
        '_run_sources',
        cancel_sources,
    )
    loop_thread = threading.get_ident()
    task = asyncio.create_task(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(tmp_path),
            initial_year=2024,
            last_year=2024,
            destination_path=str(destination),
            output_filename=output.name,
            verbose=False,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not aborted.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert aborted.is_set()
    assert output.read_bytes() == b'previous output'
    assert sorted(path.name for path in destination.iterdir()) == [output.name]


async def test_cancel_after_commit_decision_returns_verified_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publication finishes off-loop once its atomic decision has started."""
    write_cotahist_txt(tmp_path, year=2024, records=[build_cotahist_record()])
    destination = tmp_path / 'output'
    destination.mkdir()
    output = destination / 'quotes.parquet'
    pq.write_table(pa.table({'previous': [1]}), output)
    before = output.read_bytes()
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    replace = FileOperations.replace
    commit_threads = []

    def hold_publication_replacement(self, source, target):
        if target == output:
            commit_threads.append(threading.get_ident())
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=5)
        return replace(self, source, target)

    monkeypatch.setattr(
        FileOperations, 'replace', hold_publication_replacement
    )
    task = asyncio.create_task(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(tmp_path),
            initial_year=2024,
            last_year=2024,
            destination_path=str(destination),
            output_filename=output.name,
            verbose=False,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert output.read_bytes() == before
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        result = await task

    assert result['success'] is True
    assert result['total_records'] == result['integrity']['verified_rows'] == 1
    assert result['output_file'] == str(output)
    assert output.read_bytes() != before
    assert len(commit_threads) == 1
    assert commit_threads[0] != threading.get_ident()
    assert task.cancelling() == 0
    assert sorted(path.name for path in destination.iterdir()) == [output.name]
