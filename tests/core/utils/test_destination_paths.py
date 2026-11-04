from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from globaldatafinance.core.utils.destination_paths import (
    normalize_destination_path,
    prepare_writable_destination,
)
from globaldatafinance.macro_exceptions import (
    InvalidDestinationPathError,
    PathCreationError,
    PathIsNotDirectoryError,
    PathPermissionError,
    SecurityError,
)

pytestmark = pytest.mark.unit


def _prepare(path: str) -> Path:
    return prepare_writable_destination(
        path,
        type_label='Destination path',
        empty_message='path cannot be empty or whitespace',
        allowed_unc_roots=(),
    )


def test_normalize_requires_a_string_and_preserves_type_label() -> None:
    with pytest.raises(TypeError, match='Destination path must be a string'):
        normalize_destination_path(
            cast(str, 42),
            type_label='Destination path',
            empty_message='path cannot be empty',
            allowed_unc_roots=(),
        )


@pytest.mark.parametrize('value', ['', '   '])
def test_normalize_rejects_empty_paths_with_owner_message(value: str) -> None:
    with pytest.raises(
        InvalidDestinationPathError, match='path cannot be empty'
    ):
        normalize_destination_path(
            value,
            type_label='Destination path',
            empty_message='path cannot be empty',
            allowed_unc_roots=(),
        )


def test_sensitive_path_is_rejected_before_directory_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mkdir_called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal mkdir_called
        mkdir_called = True

    monkeypatch.setattr(Path, 'mkdir', fail_if_called)

    with pytest.raises(SecurityError):
        _prepare('/')

    assert mkdir_called is False


def test_existing_file_is_not_accepted_as_a_destination(
    tmp_path: Path,
) -> None:
    target = tmp_path / 'output'
    target.write_text('not a directory', encoding='utf-8')

    with pytest.raises(PathIsNotDirectoryError):
        _prepare(str(target))


def test_existing_unwritable_directory_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'output'
    target.mkdir()
    monkeypatch.setattr(os, 'access', lambda *_args: False)

    with pytest.raises(PathPermissionError):
        _prepare(str(target))


def test_permission_error_during_creation_preserves_the_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'nested' / 'output'
    original = PermissionError('creation denied')

    def deny_creation(*_args: object, **_kwargs: object) -> None:
        raise original

    monkeypatch.setattr(Path, 'mkdir', deny_creation)

    with pytest.raises(PathPermissionError) as exc_info:
        _prepare(str(target))

    assert exc_info.value.__cause__ is original


def test_generic_creation_error_preserves_the_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'nested' / 'output'
    original = OSError('filesystem unavailable')

    def fail_creation(*_args: object, **_kwargs: object) -> None:
        raise original

    monkeypatch.setattr(Path, 'mkdir', fail_creation)

    with pytest.raises(PathCreationError) as exc_info:
        _prepare(str(target))

    assert exc_info.value.__cause__ is original


def test_missing_nested_destination_is_created_and_revalidated(
    tmp_path: Path,
) -> None:
    target = tmp_path / 'one' / 'two' / 'output'

    assert _prepare(str(target)) == target.resolve()
    assert target.is_dir()


def test_post_creation_file_race_uses_directory_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'output'

    monkeypatch.setattr(Path, 'mkdir', lambda *_args, **_kwargs: None)

    with pytest.raises(PathIsNotDirectoryError):
        _prepare(str(target))


def test_post_creation_permission_recheck_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / 'output'
    monkeypatch.setattr(os, 'access', lambda *_args: False)

    with pytest.raises(PathPermissionError):
        _prepare(str(target))

    assert target.is_dir()
