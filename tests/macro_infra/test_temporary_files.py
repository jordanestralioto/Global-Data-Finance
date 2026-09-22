from __future__ import annotations

from pathlib import Path

import pytest

from globaldatafinance.macro_infra import temporary_files

pytestmark = pytest.mark.unit


def test_reservations_are_unique_sibling_files_and_caller_owned(
    tmp_path: Path,
) -> None:
    target = tmp_path / 'result.parquet'
    first = temporary_files.reserve_temporary_path(target, suffix='.part')
    second = temporary_files.reserve_temporary_path(target, suffix='.part')

    try:
        assert first != second
        assert first.parent == target.parent
        assert second.parent == target.parent
        assert first.name.startswith('.result.parquet.')
        assert first.name.endswith('.part')
        assert second.name.endswith('.part')
        assert first.is_file()
        assert second.is_file()

        with first.open('ab') as handle:
            handle.write(b'caller-owned')
        assert first.read_bytes() == b'caller-owned'
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_reservation_does_not_create_a_missing_parent(tmp_path: Path) -> None:
    parent = tmp_path / 'missing'

    with pytest.raises(FileNotFoundError):
        temporary_files.reserve_temporary_path(
            parent / 'result.parquet', suffix='.part'
        )

    assert not parent.exists()


def test_close_failure_removes_only_the_newly_reserved_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'result.parquet'
    existing = tmp_path / '.unrelated.part'
    existing.touch()
    created = tmp_path / '.result.parquet.fake.part'
    created.touch()

    def fake_mkstemp(**_kwargs: object) -> tuple[int, str]:
        return 123, str(created)

    original = OSError('close failed')

    def fail_close(_descriptor: int) -> None:
        raise original

    monkeypatch.setattr(temporary_files.tempfile, 'mkstemp', fake_mkstemp)
    monkeypatch.setattr(temporary_files.os, 'close', fail_close)

    with pytest.raises(OSError) as exc_info:
        temporary_files.reserve_temporary_path(target, suffix='.part')

    assert exc_info.value is original
    assert not created.exists()
    assert existing.exists()


def test_successful_reservation_has_no_open_descriptor(
    tmp_path: Path,
) -> None:
    reserved = temporary_files.reserve_temporary_path(
        tmp_path / 'result.parquet', suffix='.parquet.tmp'
    )
    try:
        with reserved.open('rb') as handle:
            assert handle.fileno() >= 0
        reserved.unlink()
        assert not reserved.exists()
    finally:
        reserved.unlink(missing_ok=True)
