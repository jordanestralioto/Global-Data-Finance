"""Validate container ownership, bounded hashing and independent replay."""

from __future__ import annotations

import hashlib
import zipfile
from asyncio import CancelledError
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event

import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    async_execution,
    input_validation,
    zip_reader,
)
from globaldatafinance.brazil.b3_data.historical_quotes import (
    source_validation as validation,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    index_cotahist_catalog,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from globaldatafinance.macro_exceptions import ExtractionError
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration
document = validation.document


def test_one_zip_extraction_has_two_crc_scans_and_five_decompressions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preflight owns three passes, and fresh worker validation owns two."""
    path = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    crc_calls = []
    decompressions = []
    original_crc = input_validation.validate_zip_crc_with_limits
    original_open = zipfile.ZipFile.open

    def crc(*args, **kwargs):
        crc_calls.append(args[1])
        return original_crc(*args, **kwargs)

    def open_member(archive, name, mode='r', *args, **kwargs):
        if mode == 'r':
            decompressions.append(archive)
        return original_open(archive, name, mode, *args, **kwargs)

    monkeypatch.setattr(input_validation, 'validate_zip_crc_with_limits', crc)
    monkeypatch.setattr(zipfile.ZipFile, 'open', open_member)
    result = HistoricalQuotesB3().extract(
        str(tmp_path), initial_year=2024, last_year=2024, verbose=False
    )

    assert result['success'] is True
    assert result['integrity']['verified_rows'] == 1
    assert result['integrity']['complete_market_selection'] is True
    assert len(crc_calls) == 2
    assert len(decompressions) == 5
    assert decompressions[:3] == [crc_calls[0]] * 3
    assert decompressions[3:] == [crc_calls[1]] * 2
    assert crc_calls[0] is not crc_calls[1]
    assert all(archive.fp is None for archive in crc_calls)
    assert path.is_file()


def test_standalone_index_still_validates_its_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extraction reuse does not make standalone indexing trust a pathname."""
    path = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    calls = []
    original = input_validation.validate_zip_crc_with_limits

    def crc(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(input_validation, 'validate_zip_crc_with_limits', crc)
    assert index_cotahist_catalog(tmp_path) == {2024: [path]}
    assert len(calls) == 1


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
def test_chunk_hash_preserves_exact_bytes_and_allocates_no_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extension: str
) -> None:
    """Physical terminators and chunk boundaries belong to source identity."""
    payload = (build_cotahist_record().encode('latin-1') + b'\r\n\n') * 600
    path = tmp_path / f'COTAHIST_A2024.{extension}'
    if extension == 'ZIP':
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('COTAHIST_A2024.TXT', payload)
    else:
        path.write_bytes(payload)

    def reject_context(*_args):
        pytest.fail('Hashing allocated a record context')

    monkeypatch.setattr(zip_reader, '_raw_line_with_context', reject_context)
    with zip_reader.ZipFileReaderB3()._open_source(path) as source:
        chunks = list(source.iter_chunks())
        digest, size = document._sha256_uncompressed(source)
        assert b''.join(chunks) == payload
        assert max(map(len, chunks)) == 64 * 1024
        assert digest == hashlib.sha256(payload).hexdigest()
        assert size == len(payload)
    if source.txt is not None:
        assert source.txt.closed
    if source.archive is not None:
        assert source.archive.fp is None


def test_document_resolves_member_and_rejects_explicit_mismatch(
    tmp_path: Path,
) -> None:
    """Omitting a member resolves it, while supplied evidence is checked."""
    path = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    validator = document.CotahistDocumentValidator(
        zip_reader.ZipFileReaderB3()
    )
    source = validator.validate(
        path, year=2024, target_tpmerc_codes=set(), all_markets=True
    )
    assert source.member == 'COTAHIST_A2024.TXT'
    with pytest.raises(ExtractionError, match='member changed'):
        validator.validate(
            path,
            year=2024,
            member='replaced.txt',
            target_tpmerc_codes=set(),
            all_markets=True,
        )


@pytest.mark.parametrize('replacement', ['in_place', 'rename'])
def test_source_mutation_between_hash_and_scan_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    """Both changed owned bytes and pathname replacement remain detectable."""
    path = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    changed = path.read_bytes().replace(b'PETR4', b'VALE3')
    original = document._sha256_uncompressed
    handles = []

    def mutate(source):
        handles.append(source.txt)
        result = original(source)
        if replacement == 'in_place':
            path.write_bytes(changed)
        else:
            substitute = tmp_path / 'replacement'
            substitute.write_bytes(changed)
            substitute.replace(path)
        return result

    monkeypatch.setattr(document, '_sha256_uncompressed', mutate)
    validator = document.CotahistDocumentValidator(
        zip_reader.ZipFileReaderB3()
    )
    with pytest.raises(
        ExtractionError, match='changed during catalog preflight'
    ):
        validator.validate(
            path, year=2024, target_tpmerc_codes=set(), all_markets=True
        )
    assert handles and all(handle.closed for handle in handles)


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
@pytest.mark.parametrize('entrypoint', ['validator', 'facade'])
@pytest.mark.parametrize('window', ['before_open', 'after_open'])
def test_path_replacement_at_container_open_is_rejected_in_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    entrypoint: str,
    window: str,
) -> None:
    """Outer and content identities cannot come from different open files."""
    write_source = (
        write_cotahist_txt if extension == 'TXT' else write_cotahist_zip
    )
    path = write_source(tmp_path, year=2024, records=[build_cotahist_record()])
    replacement_dir = tmp_path / 'replacement'
    replacement_dir.mkdir()
    replacement = write_source(
        replacement_dir,
        year=2024,
        records=[build_cotahist_record(ticker='VALE3')],
    )
    original_open = zip_reader.ZipFileReaderB3._open_source
    opened: list[zip_reader._OpenedCotahistSource] = []

    @contextmanager
    def replace_at_open(
        reader: zip_reader.ZipFileReaderB3,
        candidate: Path,
        *,
        expected_member: str | None = None,
    ) -> Iterator[zip_reader._OpenedCotahistSource]:
        if not opened and window == 'before_open':
            replacement.replace(candidate)
        with original_open(
            reader, candidate, expected_member=expected_member
        ) as source:
            if not opened and window == 'after_open':
                replacement.replace(candidate)
            opened.append(source)
            yield source

    monkeypatch.setattr(
        zip_reader.ZipFileReaderB3, '_open_source', replace_at_open
    )
    if entrypoint == 'validator':
        validator = document.CotahistDocumentValidator(
            zip_reader.ZipFileReaderB3()
        )
        with pytest.raises(
            ExtractionError,
            match='COTAHIST input changed during catalog preflight',
        ):
            validator.validate(
                path, year=2024, target_tpmerc_codes=set(), all_markets=True
            )
    else:
        destination = tmp_path / 'output'
        result = HistoricalQuotesB3().extract(
            str(tmp_path),
            initial_year=2024,
            last_year=2024,
            destination_path=str(destination),
            verbose=False,
        )
        assert result['success'] is False
        assert result['success_count'] == result['total_records'] == 0
        assert result['output_file'] == ''
        assert result['integrity']['status'] == 'failed'
        assert 'COTAHIST input changed during catalog preflight' in ' '.join(
            result['errors'].values()
        )
        assert not destination.exists()
    assert len(opened) == 1
    source = opened[0]
    if source.txt is not None:
        assert source.txt.closed
    if source.archive is not None:
        assert source.archive.fp is None
    assert not list(tmp_path.rglob('*.parquet'))


def test_invalid_filename_is_rejected_before_outer_identity_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capturing identity must not read an unvalidated input pathname."""
    path = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    ).rename(tmp_path / 'unsupported.TXT')

    def reject_hash(_path: Path) -> str:
        pytest.fail('Identity hashing read an invalid source filename')

    monkeypatch.setattr(document, 'sha256_file', reject_hash)
    validator = document.CotahistDocumentValidator(
        zip_reader.ZipFileReaderB3()
    )
    with pytest.raises(CotahistCatalogError, match='filename contract'):
        validator.validate(
            path, year=2024, target_tpmerc_codes=set(), all_markets=True
        )


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
def test_chunk_hash_cancellation_closes_owned_handles(
    tmp_path: Path, extension: str
) -> None:
    """Cancellation between chunks releases both stream and container."""
    records = [build_cotahist_record()] * 600
    if extension == 'TXT':
        path = write_cotahist_txt(tmp_path, year=2024, records=records)
    else:
        path = write_cotahist_zip(
            tmp_path,
            year=2024,
            records=records,
            compression=zipfile.ZIP_STORED,
        )
    stop = Event()
    token = async_execution.set_phase_cancellation(stop)
    try:
        with (
            pytest.raises(CancelledError),
            zip_reader.ZipFileReaderB3()._open_source(path) as source,
        ):
            chunks = source.iter_chunks()
            assert len(next(chunks)) == 64 * 1024
            stop.set()
            next(chunks)
    finally:
        async_execution.reset_phase_cancellation(token)
    if source.txt is not None:
        assert source.txt.closed
    if source.archive is not None:
        assert source.archive.fp is None
