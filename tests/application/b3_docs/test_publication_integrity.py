"""Failed final integrity checks preserve previously published quotations."""

import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication import (
    TransactionalPublisher,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    LOCK_NAME,
    MANIFEST_PREFIX,
    FileOperations,
)
from scripts.cotahist_oracle import reconcile_sources
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _previous_output(destination: Path) -> tuple[Path, bytes]:
    destination.mkdir()
    output = destination / 'quotes.parquet'
    pq.write_table(pa.table({'previous': ['caller-owned output']}), output)
    return output, output.read_bytes()


def _assert_failed_publication(
    result: dict, output: Path, before: bytes
) -> None:
    assert result['success'] is False
    assert result['success_count'] == result['total_records'] == 0
    assert result['output_file'] == ''
    assert result['error_count'] == 1
    assert result['integrity']['status'] == 'failed'
    assert output.read_bytes() == before
    assert not list(output.parent.glob('.globaldatafinance-transaction*'))


@pytest.mark.parametrize('mutation', ['append', 'remove'])
def test_source_mutation_after_full_readback_aborts_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """Sources must still match preflight after all staged verification."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    output, before = _previous_output(tmp_path / 'output')
    orchestrator = extraction_service.service.orchestrator
    verify_output = orchestrator.merge_and_verify_output

    def mutate_after_readback(*args, **kwargs):
        verified = verify_output(*args, **kwargs)
        if mutation == 'append':
            source.write_bytes(source.read_bytes() + b'\n')
        else:
            source.unlink()
        return verified

    monkeypatch.setattr(
        orchestrator, 'merge_and_verify_output', mutate_after_readback
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(output.parent),
        output_filename=output.name,
        verbose=False,
    )

    _assert_failed_publication(dict(result), output, before)
    expected = 'source changed' if mutation == 'append' else 'Cannot recheck'
    assert expected in ' '.join(result['errors'].values())


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['append', 'remove'])
async def test_concurrent_source_change_at_final_checkpoint_preserves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """A second caller task cannot change input before unchecked commit."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    output, before = _previous_output(tmp_path / 'output')
    checkpoint = asyncio.Event()
    changed = asyncio.Event()
    orchestrator = extraction_service.service.orchestrator
    run_publication = orchestrator.run_publication_phase

    async def observe_publication_checkpoint(verify, publish):
        checkpoint.set()
        await changed.wait()
        return await run_publication(verify, publish)

    async def change_source():
        await checkpoint.wait()
        try:
            if mutation == 'append':
                source.write_bytes(source.read_bytes() + b'\n')
            else:
                source.unlink()
        finally:
            changed.set()

    monkeypatch.setattr(
        orchestrator, 'run_publication_phase', observe_publication_checkpoint
    )
    mutator = asyncio.create_task(change_source())
    try:
        result = await HistoricalQuotesB3().extract_async(
            path_of_docs=str(tmp_path),
            initial_year=2024,
            last_year=2024,
            destination_path=str(output.parent),
            output_filename=output.name,
            verbose=False,
        )
    finally:
        mutator.cancel()
        await asyncio.gather(mutator, return_exceptions=True)

    assert checkpoint.is_set() and changed.is_set()
    _assert_failed_publication(dict(result), output, before)
    expected = 'source changed' if mutation == 'append' else 'Cannot recheck'
    assert expected in ' '.join(result['errors'].values())


@pytest.mark.parametrize('mutation', ['price', 'bytes', 'drop', 'null'])
def test_corrupt_private_parquet_never_replaces_previous_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """Actual staged file corruption is caught by production readback."""
    source = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[
            build_cotahist_record(),
            build_cotahist_record(ticker='VALE3'),
        ],
    )
    source_before = source.read_bytes()
    output, before = _previous_output(tmp_path / 'output')
    processor = extraction_service.zip_processor.ZipProcessorB3
    process_source = processor.process

    def corrupt_private_output(self, *args, **kwargs):
        result = process_source(self, *args, **kwargs)
        assert result.temp_path is not None
        table = pq.read_table(result.temp_path)
        rows = table.to_pylist()
        if mutation == 'price':
            rows[0]['preco_abertura'] = Decimal('999.99')
        elif mutation == 'bytes':
            rows[0]['registro_original'] = b'X' * 245
        elif mutation == 'null':
            rows[0]['ticker'] = None
        else:
            rows.pop()
        schema = table.schema
        if mutation == 'null':
            index = schema.get_field_index('ticker')
            schema = schema.set(index, schema.field(index).with_nullable(True))
        pq.write_table(
            pa.Table.from_pylist(rows, schema=schema), result.temp_path
        )
        return result

    monkeypatch.setattr(processor, 'process', corrupt_private_output)

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(output.parent),
        output_filename=output.name,
        verbose=False,
    )

    _assert_failed_publication(dict(result), output, before)
    assert source.read_bytes() == source_before


@pytest.mark.parametrize('cleanup_failures', [1, 2])
def test_postcommit_cleanup_failure_preserves_truthful_success_and_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_failures: int,
) -> None:
    """Derived-state cleanup cannot erase a verified committed outcome."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    output, before = _previous_output(tmp_path / 'output')
    remove_tree = FileOperations.rmtree
    begin = TransactionalPublisher.begin
    transactions = []
    remaining = cleanup_failures

    def record_transaction(self, **kwargs):
        transaction = begin(self, **kwargs)
        transactions.append(transaction)
        return transaction

    def fail_derived_cleanup(self, path):
        nonlocal remaining
        if (
            path.name.startswith(MANIFEST_PREFIX)
            and path.name != LOCK_NAME
            and remaining
        ):
            remaining -= 1
            raise OSError('injected postcommit cleanup failure')
        return remove_tree(self, path)

    monkeypatch.setattr(TransactionalPublisher, 'begin', record_transaction)
    monkeypatch.setattr(FileOperations, 'rmtree', fail_derived_cleanup)

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(output.parent),
        output_filename=output.name,
        verbose=False,
    )

    assert result['success'] is True
    assert result['success_count'] == result['total_records'] == 1
    assert result['error_count'] == 0
    assert result['errors'] == {}
    assert result['output_file'] == str(output)
    assert output.read_bytes() != before
    assert result['integrity']['status'] == 'passed'
    assert result['integrity']['verified_rows'] == 1
    assert (
        result['integrity']['output_sha256']
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    warning = result['integrity']['warnings'][-1]
    assert warning['code'] == (
        'PUBLICATION_CLEANUP_RECOVERED'
        if cleanup_failures == 1
        else 'PUBLICATION_CLEANUP_PENDING'
    )
    assert warning['source'] == output.name
    assert warning['count'] == 1
    assert 'injected postcommit cleanup failure' in warning['explanation']
    assert (
        reconcile_sources([source], output, public_result=dict(result))[
            'verifiedRows'
        ]
        == 1
    )
    leftovers = list(output.parent.glob('.globaldatafinance-transaction*'))
    assert bool(leftovers) is (cleanup_failures == 2)
    published_bytes = output.read_bytes()
    transactions[0].abort()
    assert output.read_bytes() == published_bytes
    assert not list(output.parent.glob('.globaldatafinance-transaction*'))


def test_failure_before_durable_commit_restores_previous_public_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An actual replacement failure retains rollback and failed counters."""
    write_cotahist_txt(tmp_path, year=2024, records=[build_cotahist_record()])
    output, before = _previous_output(tmp_path / 'output')
    replace = FileOperations.replace
    failed = False

    def fail_first_replacement(self, source, destination):
        nonlocal failed
        if destination == output and not failed:
            failed = True
            raise OSError('injected precommit replacement failure')
        return replace(self, source, destination)

    monkeypatch.setattr(FileOperations, 'replace', fail_first_replacement)

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        destination_path=str(output.parent),
        output_filename=output.name,
        verbose=False,
    )

    _assert_failed_publication(dict(result), output, before)
    assert (
        'injected precommit replacement failure'
        in result['errors']['transaction']
    )


def _checked_transaction(destination: Path):
    output, before = _previous_output(destination)
    publication = TransactionalPublisher(destination, owner='b3').begin()
    staged = publication.stage_path(output.name)
    table = pa.table({'verified': [Decimal('12.34')]})
    pq.write_table(table, staged)
    assert pq.read_table(staged).equals(table)
    publication.add_artifact(
        final_path=output,
        staged_path=staged,
        expected_rows=1,
        schema_fingerprint='verified-test-schema',
    )
    publication.mark_validated()
    return publication, output, before, staged.read_bytes()


@pytest.mark.parametrize('failures', [1, 2])
def test_committed_cleanup_phase_preserves_validated_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failures: int,
) -> None:
    """Cleanup recovery and pending cleanup retain exact committed bytes."""
    publication, output, before, checked = _checked_transaction(
        tmp_path / 'destination'
    )
    remaining = failures
    remove_tree = FileOperations.rmtree

    def interrupt_cleanup(self, path):
        nonlocal remaining
        if path == publication.staging_dir and remaining:
            remaining -= 1
            raise OSError('injected committed cleanup failure')
        return remove_tree(self, path)

    monkeypatch.setattr(FileOperations, 'rmtree', interrupt_cleanup)
    commit = extraction_service.service.publication.commit_with_cleanup_warning
    warning = commit(publication)

    assert warning is not None
    assert warning['code'] == (
        'PUBLICATION_CLEANUP_RECOVERED'
        if failures == 1
        else 'PUBLICATION_CLEANUP_PENDING'
    )
    assert warning['source'] == output.name
    assert isinstance(warning['explanation'], str)
    assert 'injected committed cleanup failure' in warning['explanation']
    assert output.read_bytes() == checked != before
    assert bool(
        list(output.parent.glob('.globaldatafinance-transaction*'))
    ) is (failures == 2)
    publication.abort()
    assert output.read_bytes() == checked
    assert not list(output.parent.glob('.globaldatafinance-transaction*'))


def test_commit_marker_write_failure_still_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-memory COMMITTED phase cannot claim an undurable commit."""
    publication, output, before, _checked = _checked_transaction(
        tmp_path / 'destination'
    )
    write_bytes = FileOperations.write_bytes
    failure_count = []

    def reject_commit_marker(self, path, payload):
        if json.loads(payload).get('phase') == 'COMMITTED':
            failure_count.append(True)
            raise OSError('injected durable commit marker failure')
        return write_bytes(self, path, payload)

    monkeypatch.setattr(FileOperations, 'write_bytes', reject_commit_marker)
    commit = extraction_service.service.publication.commit_with_cleanup_warning

    with pytest.raises(ExtractionError, match='commit marker failure'):
        commit(publication)

    assert failure_count == [True]
    assert output.read_bytes() == before
    assert publication.manifest.phase == 'ROLLED_BACK'
    assert not list(output.parent.glob('.globaldatafinance-transaction*'))
