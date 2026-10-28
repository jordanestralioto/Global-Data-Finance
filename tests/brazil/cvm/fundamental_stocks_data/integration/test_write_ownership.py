"""CVM source ownership under concurrent writers and interrupted attempts."""

from __future__ import annotations

import errno
import multiprocessing
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    destination_io,
    download_finalization,
    download_validation,
    transaction,
    write_ownership,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    http as cvm_http,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import ExtractionError, SecurityError

pytestmark = pytest.mark.integration


def _archive(path: Path, identifier: str) -> Path:
    """Create a source distinguishable from a competing attempt's archive."""
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('data.csv', f'id\n{identifier}\n'.encode())
    return path


def _finalize(stage: Path, final: Path, extractor):
    """Exercise the real validation, promotion, and extraction boundary."""
    return download_finalization.finalize_downloaded_file(
        stage,
        final,
        str(final.parent),
        'DFP',
        '2024',
        automatic_extractor=True,
        file_extractor_repository=extractor,
        validate_file=download_validation.validate_downloaded_file,
        cleanup_file=lambda path: Path(path).unlink(missing_ok=True),
    )


def test_competing_finalizer_cannot_replace_the_archive_being_extracted(
    tmp_path: Path,
) -> None:
    """A conflicting writer fails before changing the first writer's ZIP."""
    first = _archive(tmp_path / 'first.part', '0001')
    second = _archive(tmp_path / 'second.part', '0002')
    first_bytes = first.read_bytes()
    final = tmp_path / 'dfp_cia_aberta_2024.zip'
    started = threading.Event()
    continue_extraction = threading.Event()

    class PausedExtractor:
        def extract(self, source_path: str, destination_path: str) -> None:
            started.set()
            assert continue_extraction.wait(timeout=5)
            ParquetExtractorAdapterCVM().extract(source_path, destination_path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        active = executor.submit(_finalize, first, final, PausedExtractor())
        try:
            assert started.wait(timeout=5)
            rejected = _finalize(second, final, ParquetExtractorAdapterCVM())
            assert rejected.succeeded is False
            assert 'active or unrecovered writer' in rejected.error_message
            assert final.read_bytes() == first_bytes
            assert not second.exists()
        finally:
            continue_extraction.set()
        accepted = active.result(timeout=5)

    assert accepted.succeeded is True
    assert final.read_bytes() == first_bytes
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '0001'}
    ]
    assert not (tmp_path / write_ownership.LOCK_NAME).exists()


def _competing_process(
    source: str, destination: str, result_path: str
) -> None:
    """Run the normal public source adapter in a separate interpreter."""
    try:
        ParquetExtractorAdapterCVM().extract(source, destination)
    except ExtractionError as error:
        Path(result_path).write_text(str(error), encoding='utf-8')
    else:
        Path(result_path).write_text('unexpected success', encoding='utf-8')


def test_destination_ownership_is_shared_across_processes(
    tmp_path: Path,
) -> None:
    """A fresh interpreter cannot bypass the parent process's lease."""
    source = _archive(tmp_path / 'source.zip', '0001')
    context = multiprocessing.get_context('spawn')
    result_path = tmp_path / 'process-result.txt'
    process = context.Process(
        target=_competing_process,
        args=(str(source), str(tmp_path), str(result_path)),
    )
    with write_ownership.exclusive_destination(str(tmp_path)):
        process.start()
        try:
            process.join(timeout=10)
            assert process.exitcode == 0
            message = result_path.read_text(encoding='utf-8')
            assert 'active or unrecovered writer' in message
            assert not (tmp_path / 'data.parquet').exists()
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '0001'}
    ]


def test_unrecovered_lease_requires_explicit_inspection(
    tmp_path: Path,
) -> None:
    """Unverifiable lock state is preserved instead of guessed to be stale."""
    lock = tmp_path / write_ownership.LOCK_NAME
    lock.mkdir()
    (lock / 'owner.json').write_text('{"pid": 0}', encoding='utf-8')
    source = _archive(tmp_path / 'source.zip', '0001')
    original = source.read_bytes()

    with pytest.raises(ExtractionError, match='unrecovered writer'):
        ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert source.read_bytes() == original
    assert (lock / 'owner.json').read_text() == '{"pid": 0}'
    assert not (tmp_path / 'data.parquet').exists()


def test_conflicting_finalizer_never_cleans_a_caller_owned_archive(
    tmp_path: Path,
) -> None:
    """A direct final-path input must remain intact when ownership fails."""
    source = _archive(tmp_path / 'source.zip', '0001')
    original = source.read_bytes()
    (tmp_path / write_ownership.LOCK_NAME).mkdir()
    rejected = _finalize(source, source, ParquetExtractorAdapterCVM())
    assert rejected.succeeded is False
    assert 'active or unrecovered writer' in rejected.error_message
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize('destination_state', ['missing', 'file'])
async def test_changed_destination_does_not_abort_other_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destination_state: str,
) -> None:
    """An invalidated output directory cannot abort independent documents."""
    invalid_destination = tmp_path / 'invalid'
    valid_destination = tmp_path / 'valid'
    invalid_destination.mkdir()
    valid_destination.mkdir()
    adapter = AsyncDownloadAdapterCVM(
        file_extractor_repository=ParquetExtractorAdapterCVM(),
        max_concurrent=1,
    )

    async def stream_archive(url: str, filepath: str) -> Path:
        staging = _archive(Path(filepath + '.part'), '00123')
        if url.endswith('2024.zip'):
            (invalid_destination / 'dfp_cia_aberta_2024.zip.part').unlink()
            invalid_destination.rmdir()
            if destination_state == 'file':
                invalid_destination.write_bytes(b'replaced destination')
        return staging

    monkeypatch.setattr(adapter, '_stream_download', stream_archive)
    result = await adapter.async_download_docs(
        [
            (
                'https://example.test/dfp_cia_aberta_2024.zip',
                'DFP',
                '2024',
                str(invalid_destination),
            ),
            (
                'https://example.test/dfp_cia_aberta_2025.zip',
                'DFP',
                '2025',
                str(valid_destination),
            ),
        ],
        automatic_extractor=True,
    )

    assert result.successful_downloads == ['DFP_2025']
    assert result.error_count_downloads == 1
    assert 'Destination path' in result.failed_downloads['DFP_2024']
    assert not (invalid_destination / 'dfp_cia_aberta_2024.zip').exists()
    assert pq.read_table(valid_destination / 'data.parquet').to_pylist() == [
        {'id': '00123'}
    ]
    assert not list(valid_destination.glob('*.part'))
    assert not (valid_destination / write_ownership.LOCK_NAME).exists()
    if destination_state == 'file':
        assert invalid_destination.read_bytes() == b'replaced destination'


def test_invalid_destination_never_cleans_a_caller_owned_archive(
    tmp_path: Path,
) -> None:
    """A lease failure retains caller-owned input and its diagnostic."""
    source = _archive(tmp_path / 'source.zip', '0001')
    original = source.read_bytes()
    invalid_destination = tmp_path / 'destination'
    invalid_destination.write_bytes(b'caller-owned destination')

    rejected = download_finalization.finalize_downloaded_file(
        source,
        source,
        str(invalid_destination),
        'DFP',
        '2024',
        automatic_extractor=False,
        file_extractor_repository=None,
        validate_file=download_validation.validate_downloaded_file,
        cleanup_file=lambda path: Path(path).unlink(missing_ok=True),
    )

    assert rejected.succeeded is False
    assert rejected.error_message is not None
    assert 'must be a directory' in rejected.error_message
    assert source.read_bytes() == original
    assert invalid_destination.read_bytes() == b'caller-owned destination'


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_failure', [False, True])
async def test_redirected_destination_preserves_unowned_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_failure: bool,
) -> None:
    """A replaced parent cannot authorize foreign writes or cleanup."""
    destination = tmp_path / 'destination'
    original_destination = tmp_path / 'original-destination'
    outside_destination = tmp_path / 'outside'
    destination.mkdir()
    outside_destination.mkdir()
    filename = 'dfp_cia_aberta_2024.zip'
    staging_name = filename + '.part'
    foreign_staging = outside_destination / staging_name
    foreign_staging.write_bytes(b'caller-owned foreign file')
    adapter = AsyncDownloadAdapterCVM(
        file_extractor_repository=ParquetExtractorAdapterCVM()
    )

    async def stream_archive(_url: str, filepath: str) -> Path:
        return _archive(Path(filepath + '.part'), '00123')

    resolve_extractor = cvm_http.resolve_parquet_extractor

    def redirect_destination(repository, **options):
        destination.rename(original_destination)
        destination.symlink_to(outside_destination, target_is_directory=True)
        if provider_failure:
            raise RuntimeError('extractor provider closed')
        return resolve_extractor(repository, **options)

    monkeypatch.setattr(adapter, '_stream_download', stream_archive)
    monkeypatch.setattr(
        cvm_http, 'resolve_parquet_extractor', redirect_destination
    )
    error_type = RuntimeError if provider_failure else SecurityError
    message = 'extractor provider closed' if provider_failure else 'changed'
    with pytest.raises(error_type, match=message):
        await adapter.async_download_docs(
            [
                (
                    'https://example.test/' + filename,
                    'DFP',
                    '2024',
                    str(destination),
                )
            ],
            automatic_extractor=True,
        )

    assert foreign_staging.read_bytes() == b'caller-owned foreign file'
    assert (original_destination / staging_name).is_file()
    assert not (outside_destination / filename).exists()
    assert not (outside_destination / 'data.parquet').exists()
    assert not (outside_destination / write_ownership.LOCK_NAME).exists()


@pytest.mark.parametrize('swap_phase', ['validation', 'promotion'])
def test_parent_swap_during_finalization_preserves_foreign_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_phase: str,
) -> None:
    """Late parent substitution cannot redirect promotion or lock cleanup."""
    destination = tmp_path / 'destination'
    original_destination = tmp_path / 'original'
    outside = tmp_path / 'outside'
    destination.mkdir()
    outside.mkdir()
    staging = _archive(destination / 'download.part', '00123')
    original_bytes = staging.read_bytes()
    final = destination / 'download.zip'
    (outside / staging.name).write_bytes(b'foreign staging sentinel')
    (outside / final.name).write_bytes(b'foreign final sentinel')

    def swap_parent() -> None:
        destination.rename(original_destination)
        destination.symlink_to(outside, target_is_directory=True)

    def validate_then_swap(filepath: str) -> bool:
        valid = download_validation.validate_downloaded_file(filepath)
        if swap_phase == 'validation':
            swap_parent()
        return valid

    original_replace = destination_io.DestinationFileOperationsCVM.replace

    def replace_after_swap(self, source: Path, target: Path) -> None:
        swap_parent()
        original_replace(self, source, target)

    if swap_phase == 'promotion':
        monkeypatch.setattr(
            destination_io.DestinationFileOperationsCVM,
            'replace',
            replace_after_swap,
        )

    snapshot = destination_io.capture_download_destination(destination)
    with pytest.raises(SecurityError, match='changed'):
        download_finalization.finalize_downloaded_file(
            staging,
            final,
            str(destination),
            'DFP',
            '2024',
            automatic_extractor=False,
            file_extractor_repository=None,
            validate_file=validate_then_swap,
            cleanup_file=lambda filepath: (
                destination_io.remove_owned_staging_file(
                    filepath, destination=snapshot
                )
            ),
            expected_destination=snapshot,
        )

    assert (outside / staging.name).read_bytes() == b'foreign staging sentinel'
    assert (outside / final.name).read_bytes() == b'foreign final sentinel'
    preserved_name = final.name if swap_phase == 'promotion' else staging.name
    assert (
        original_destination / preserved_name
    ).read_bytes() == original_bytes
    assert not (original_destination / write_ownership.LOCK_NAME).exists()


def test_parent_swap_during_cleanup_preserves_foreign_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup uses the opened directory even if its pathname changes."""
    destination = tmp_path / 'destination'
    original_destination = tmp_path / 'original'
    outside = tmp_path / 'outside'
    destination.mkdir()
    outside.mkdir()
    staging = destination / 'download.part'
    staging.write_bytes(b'owned staging')
    foreign = outside / staging.name
    foreign.write_bytes(b'foreign staging')
    snapshot = destination_io.capture_download_destination(destination)
    original_unlink = destination_io.DestinationFileOperationsCVM.unlink

    def unlink_after_swap(self, path: Path) -> None:
        destination.rename(original_destination)
        destination.symlink_to(outside, target_is_directory=True)
        original_unlink(self, path)

    monkeypatch.setattr(
        destination_io.DestinationFileOperationsCVM,
        'unlink',
        unlink_after_swap,
    )
    destination_io.remove_owned_staging_file(
        str(staging), destination=snapshot
    )

    assert foreign.read_bytes() == b'foreign staging'
    assert not (original_destination / staging.name).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_errno', [errno.EACCES, errno.ENOSPC])
async def test_lease_io_failure_preserves_existing_zip_and_other_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_errno: int,
) -> None:
    """A late lease I/O error cannot cancel an independent document."""
    invalid = tmp_path / 'invalid'
    valid = tmp_path / 'valid'
    invalid.mkdir()
    valid.mkdir()
    original_final = invalid / 'dfp_cia_aberta_2024.zip'
    original_final.write_bytes(b'previous caller-owned archive')
    failure = OSError(failure_errno, 'injected lease failure')
    original_mkdir = destination_io.DestinationFileOperationsCVM.mkdir

    def fail_lease(self, path: Path, *, mode: int = 0o777) -> None:
        if path == invalid / write_ownership.LOCK_NAME:
            raise failure
        original_mkdir(self, path, mode=mode)

    async def stream_archive(_url: str, filepath: str) -> Path:
        return _archive(Path(filepath + '.part'), '00123')

    monkeypatch.setattr(
        destination_io.DestinationFileOperationsCVM, 'mkdir', fail_lease
    )
    adapter = AsyncDownloadAdapterCVM(
        file_extractor_repository=ParquetExtractorAdapterCVM(),
        max_concurrent=1,
    )
    monkeypatch.setattr(adapter, '_stream_download', stream_archive)
    result = await adapter.async_download_docs(
        [
            (
                'https://example.test/dfp_cia_aberta_2024.zip',
                'DFP',
                '2024',
                str(invalid),
            ),
            (
                'https://example.test/dfp_cia_aberta_2025.zip',
                'DFP',
                '2025',
                str(valid),
            ),
        ],
        automatic_extractor=True,
    )

    assert result.successful_downloads == ['DFP_2025']
    assert result.error_count_downloads == 1
    assert 'injected lease failure' in result.failed_downloads['DFP_2024']
    assert original_final.read_bytes() == b'previous caller-owned archive'
    assert not list(invalid.glob('*.part'))
    assert pq.read_table(valid / 'data.parquet').to_pylist() == [
        {'id': '00123'}
    ]


@pytest.mark.parametrize('swap_phase', ['extractor', 'conversion'])
def test_automatic_extraction_rejects_redirected_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_phase: str,
) -> None:
    """An extraction interleaving cannot consume or write foreign artifacts."""
    destination = tmp_path / 'destination'
    original_destination = tmp_path / 'original'
    outside = tmp_path / 'outside'
    destination.mkdir()
    outside.mkdir()
    source = _archive(destination / 'source.part', 'OWNED')
    source_bytes = source.read_bytes()
    final = destination / 'source.zip'
    foreign_source = _archive(outside / final.name, 'FOREIGN')
    foreign_bytes = foreign_source.read_bytes()
    foreign_output = outside / 'data.parquet'
    foreign_output.write_bytes(b'foreign output sentinel')

    def swap_parent() -> None:
        destination.rename(original_destination)
        destination.symlink_to(outside, target_is_directory=True)

    class InterleavedExtractor:
        def extract(self, source_path: str, destination_path: str) -> None:
            if swap_phase == 'extractor':
                swap_parent()
            ParquetExtractorAdapterCVM().extract(source_path, destination_path)

    original_convert = transaction.CvmCsvParquetPipeline.convert

    def convert_after_swap(self, **kwargs):
        swap_parent()
        return original_convert(self, **kwargs)

    if swap_phase == 'conversion':
        monkeypatch.setattr(
            transaction.CvmCsvParquetPipeline, 'convert', convert_after_swap
        )
    snapshot = destination_io.capture_download_destination(destination)
    with pytest.raises(SecurityError, match='changed'):
        download_finalization.finalize_downloaded_file(
            source,
            final,
            str(destination),
            'DFP',
            '2024',
            automatic_extractor=True,
            file_extractor_repository=InterleavedExtractor(),
            validate_file=download_validation.validate_downloaded_file,
            cleanup_file=lambda path: destination_io.remove_owned_staging_file(
                path, destination=snapshot
            ),
            expected_destination=snapshot,
        )

    assert foreign_source.read_bytes() == foreign_bytes
    assert foreign_output.read_bytes() == b'foreign output sentinel'
    assert (original_destination / final.name).read_bytes() == source_bytes
    assert not (original_destination / write_ownership.LOCK_NAME).exists()


def test_no_descriptor_support_preserves_normal_extraction_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Platforms using path operations retain source, rows, and cleanup."""
    monkeypatch.setattr(
        destination_io, '_supports_directory_descriptors', lambda: False
    )
    source = _archive(tmp_path / 'source.zip', '00123')
    source_bytes = source.read_bytes()

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert source.read_bytes() == source_bytes
    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '00123'}
    ]
    assert not (tmp_path / write_ownership.LOCK_NAME).exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction-*'))


@pytest.mark.parametrize('source_in_destination', [True, False])
def test_missing_descriptor_paths_rejects_extraction_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_in_destination: bool,
) -> None:
    """Missing descriptor bridges cannot reopen a mutable destination path."""
    destination = tmp_path / 'destination'
    outside = tmp_path / 'outside'
    destination.mkdir()
    outside.mkdir()
    source_parent = destination if source_in_destination else tmp_path
    source = _archive(source_parent / 'source.zip', 'OWNED')
    source_bytes = source.read_bytes()
    foreign_source = _archive(outside / source.name, 'OTHER')
    foreign_bytes = foreign_source.read_bytes()
    foreign_output = outside / 'data.parquet'
    foreign_output.write_bytes(b'foreign output sentinel')
    original_stat = Path.stat

    def hide_descriptor_paths(path: Path, *args, **kwargs):
        if path.parent in (Path('/proc/self/fd'), Path('/dev/fd')):
            raise FileNotFoundError('Descriptor paths are unavailable')
        return original_stat(path, *args, **kwargs)

    original_convert = transaction.CvmCsvParquetPipeline.convert

    def convert_after_swap(self, **kwargs):
        destination.rename(tmp_path / 'original')
        destination.symlink_to(outside, target_is_directory=True)
        return original_convert(self, **kwargs)

    monkeypatch.setattr(Path, 'stat', hide_descriptor_paths)
    monkeypatch.setattr(
        transaction.CvmCsvParquetPipeline, 'convert', convert_after_swap
    )

    with pytest.raises(SecurityError, match='descriptor-backed'):
        ParquetExtractorAdapterCVM().extract(str(source), str(destination))

    assert source.read_bytes() == source_bytes
    assert foreign_source.read_bytes() == foreign_bytes
    assert foreign_output.read_bytes() == b'foreign output sentinel'
    assert not list(outside.glob('.globaldatafinance-transaction-*'))
    assert not (destination / write_ownership.LOCK_NAME).exists()
    assert not list(destination.glob('.globaldatafinance-transaction-*'))
