"""Final worker verification protects publication and cancellation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from threading import Event, Lock

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    ZipFileReaderB3,
    async_execution,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    TransactionalPublisher,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _prepared_publication(tmp_path: Path):
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    descriptor = resolve_cotahist_sources(
        tmp_path, expected_years={2024}, target_tpmerc_codes={'010'}
    ).sources[0]
    destination = tmp_path / 'output'
    destination.mkdir()
    output = destination / 'quotes.parquet'
    output.write_bytes(b'previous caller output')
    publication = TransactionalPublisher(destination, owner='b3').begin()
    staged = publication.stage_path(output.name)
    result = extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
        source, {'010'}, staged, source_descriptor=descriptor
    )
    table = pq.read_table(staged)
    assert table['registro_original'].to_pylist() == [
        build_cotahist_record().encode('latin-1')
    ]
    publication.add_artifact(
        final_path=output,
        staged_path=staged,
        expected_rows=result.written_records,
        schema_fingerprint=result.schema_fingerprint,
    )
    return source, descriptor, publication, output, staged.read_bytes()


@pytest.mark.parametrize('mutation', ['append', 'remove'])
def test_changed_source_cannot_cross_final_publication_decision(
    tmp_path: Path, mutation: str
) -> None:
    """The actual last source check rejects drift before any replacement."""
    source, descriptor, publication, output, _checked = _prepared_publication(
        tmp_path
    )
    if mutation == 'append':
        source.write_bytes(source.read_bytes() + b'\n')
    else:
        source.unlink()
    decision = Event()
    boundary = extraction_service.service.publication
    try:
        with pytest.raises(ExtractionError, match='source'):
            async_execution._verify_and_publish(
                partial(boundary.verify_source_files, [descriptor]),
                partial(boundary.mark_validated_and_commit, publication),
                decision,
                Lock(),
            )
        assert not decision.is_set()
        assert publication.manifest.phase == 'OPEN'
        assert output.read_bytes() == b'previous caller output'
    finally:
        publication.abort()
    assert sorted(path.name for path in output.parent.iterdir()) == [
        output.name
    ]


def test_cancellation_and_publication_decision_share_one_transition(
    tmp_path: Path,
) -> None:
    """Cancellation cannot change state halfway through the decision."""
    _source, descriptor, publication, output, checked = _prepared_publication(
        tmp_path
    )
    observe = Event()
    checkpoint = Event()
    release = Event()
    cancellation_requested = Event()
    decision = Event()
    decision_lock = Lock()
    observed_decisions = []
    boundary = extraction_service.service.publication

    class ObservedStop(Event):
        """Pause an actual stop observation at the decision boundary."""

        def is_set(self):
            value = super().is_set()
            if observe.is_set():
                checkpoint.set()
                assert release.wait(timeout=5)
            return value

    stop = ObservedStop()

    def verify():
        boundary.verify_source_files([descriptor])
        observe.set()

    def request_cancellation():
        assert checkpoint.wait(timeout=5)
        cancellation_requested.set()
        with decision_lock:
            observed_decisions.append(decision.is_set())
            stop.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            worker = executor.submit(
                async_execution._run_phase,
                stop,
                partial(
                    async_execution._verify_and_publish,
                    verify,
                    partial(boundary.mark_validated_and_commit, publication),
                    decision,
                    decision_lock,
                ),
            )
            cancellation = executor.submit(request_cancellation)
            try:
                assert cancellation_requested.wait(timeout=5)
                available = decision_lock.acquire(blocking=False)
                if available:
                    decision_lock.release()
                assert available is False
            finally:
                release.set()
            assert worker.result(timeout=5) is None
            cancellation.result(timeout=5)
        assert observed_decisions == [True]
        assert stop.is_set()
        assert output.read_bytes() == checked
    finally:
        release.set()
        publication.abort()
    assert sorted(path.name for path in output.parent.iterdir()) == [
        output.name
    ]


def test_cancel_after_source_check_prevents_publication(
    tmp_path: Path,
) -> None:
    """Cancellation observed at the last checkpoint preserves old output."""
    _source, descriptor, publication, output, _checked = _prepared_publication(
        tmp_path
    )
    stop = Event()
    decision = Event()
    boundary = extraction_service.service.publication

    def verify_then_cancel():
        boundary.verify_source_files([descriptor])
        stop.set()

    token = async_execution._phase_stop.set(stop)
    try:
        with pytest.raises(asyncio.CancelledError):
            async_execution._verify_and_publish(
                verify_then_cancel,
                partial(boundary.mark_validated_and_commit, publication),
                decision,
                Lock(),
            )
        assert not decision.is_set()
        assert output.read_bytes() == b'previous caller output'
    finally:
        async_execution._phase_stop.reset(token)
        publication.abort()
    assert sorted(path.name for path in output.parent.iterdir()) == [
        output.name
    ]


def test_verified_source_publishes_exact_staged_bytes(tmp_path: Path) -> None:
    """The decision commits the actual source-derived Parquet unchanged."""
    source, descriptor, publication, output, checked = _prepared_publication(
        tmp_path
    )
    decision = Event()
    boundary = extraction_service.service.publication
    try:
        warning = async_execution._verify_and_publish(
            partial(boundary.verify_source_files, [descriptor]),
            partial(boundary.mark_validated_and_commit, publication),
            decision,
            Lock(),
        )
        assert warning is None
        assert decision.is_set()
        assert publication.manifest.phase in {'COMMITTED', 'CLEANUP_PENDING'}
        assert output.read_bytes() == checked
        assert pq.read_table(output).num_rows == 1
        assert source.exists()
    finally:
        publication.abort()
    assert sorted(path.name for path in output.parent.iterdir()) == [
        output.name
    ]
