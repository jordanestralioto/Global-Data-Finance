"""CVM extraction on descriptor filesystems without child path traversal."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    destination_io,
    write_ownership,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_exceptions import SecurityError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures('non_traversable_descriptors'),
]


@pytest.fixture
def non_traversable_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model macOS descriptor entries that cannot resolve child paths."""
    if not destination_io._supports_directory_descriptors():
        return
    original_stat = os.stat
    original_open = io.open
    original_descriptor_open = os.open

    def reject_descriptor_children(path: Any) -> None:
        if not isinstance(path, (str, os.PathLike)):
            return
        value = os.fspath(path)
        if value.startswith('/proc/self/fd/') or (
            value.startswith('/dev/fd/')
            and '/' in value.removeprefix('/dev/fd/')
        ):
            raise FileNotFoundError(2, 'Descriptor child lookup failed', value)

    def stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        reject_descriptor_children(path)
        return original_stat(path, *args, **kwargs)

    def open_file(path: Any, *args: Any, **kwargs: Any) -> Any:
        reject_descriptor_children(path)
        return original_open(path, *args, **kwargs)

    def open_descriptor(path: Any, *args: Any, **kwargs: Any) -> int:
        reject_descriptor_children(path)
        return original_descriptor_open(path, *args, **kwargs)

    monkeypatch.setattr(os, 'stat', stat)
    monkeypatch.setattr(io, 'open', open_file)
    monkeypatch.setattr(os, 'open', open_descriptor)
    monkeypatch.setattr(
        os, 'supports_dir_fd', os.supports_dir_fd | {open_descriptor}
    )


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('encoding', ['utf-8', 'cp1252'])
def test_extraction_preserves_data_without_descriptor_child_paths(
    tmp_path: Path,
    existing: bool,
    encoding: str,
) -> None:
    """Unsupported traversal retains ZIP bytes, exact rows, and cleanup."""
    source = tmp_path / 'source.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr(
            'data.csv', 'id;name\n00123;ação\u2013\n'.encode(encoding)
        )
    source_bytes = source.read_bytes()
    caller = tmp_path / 'caller.txt'
    caller.write_bytes(b'caller-owned bytes')
    if existing:
        (tmp_path / 'data.parquet').write_bytes(b'previous output')

    ParquetExtractorAdapterCVM().extract(str(source), str(tmp_path))

    assert pq.read_table(tmp_path / 'data.parquet').to_pylist() == [
        {'id': '00123', 'name': 'ação\u2013'}
    ]
    assert source.read_bytes() == source_bytes
    assert caller.read_bytes() == b'caller-owned bytes'
    assert not (tmp_path / write_ownership.LOCK_NAME).exists()
    assert not list(tmp_path.glob('.globaldatafinance-transaction*'))


def test_path_fallback_rejects_replaced_destination(tmp_path: Path) -> None:
    """Fallback operations reject a replacement directory before writing."""
    destination = tmp_path / 'destination'
    destination.mkdir()
    snapshot = destination_io.capture_download_destination(destination)
    with destination_io.open_download_destination(snapshot) as operations:
        assert operations.descriptor is None
        destination.rename(tmp_path / 'original')
        destination.mkdir()
        foreign = destination / 'caller.txt'
        foreign.write_bytes(b'foreign bytes')

        with pytest.raises(SecurityError, match='changed'):
            operations.write_bytes(foreign, b'overwritten bytes')

    assert foreign.read_bytes() == b'foreign bytes'
    assert not (tmp_path / 'original' / foreign.name).exists()
