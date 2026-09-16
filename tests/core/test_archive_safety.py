"""Regression coverage for shared ZIP metadata and streaming limits."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import Path
from typing import cast

import pytest

from globaldatafinance.core.archive_names import validate_portable_basename
from globaldatafinance.core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
    validate_zip_archive,
    validate_zip_crc_with_limits,
)
from globaldatafinance.macro_exceptions import CorruptedZipError
from tests.support.builders import write_zip

_RESERVED_WIN32_BASENAMES = (
    'CON.zip',
    'aux.txt',
    'COM1.csv',
    'COM¹.csv',
    'COM².csv',
    'COM³.csv',
    'LPT1.csv',
    'LPT¹.csv',
    'LPT².csv',
    'LPT³.csv',
    'CONIN$.csv',
    'CONOUT$.csv',
)


def _limits(
    *,
    max_archive_bytes: int = 1_000_000,
    max_members: int = 10,
    max_member_uncompressed_bytes: int = 100_000,
    max_total_uncompressed_bytes: int = 200_000,
    max_compression_ratio: float = 200.0,
) -> ArchiveSafetyLimits:
    """Build a typed, bounded policy for one archive test."""
    return ArchiveSafetyLimits(
        max_archive_bytes=max_archive_bytes,
        max_members=max_members,
        max_member_uncompressed_bytes=max_member_uncompressed_bytes,
        max_total_uncompressed_bytes=max_total_uncompressed_bytes,
        max_compression_ratio=max_compression_ratio,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ('members', 'limits', 'reason'),
    [
        (
            {'one.csv': 'a;b\n1;2\n', 'two.csv': 'a;b\n3;4\n'},
            _limits(max_members=1),
            'member count',
        ),
        (
            {'../escape.csv': 'a;b\n1;2\n'},
            _limits(),
            'unsafe ZIP member path',
        ),
        (
            {'Foo.csv': 'a;b\n1;2\n', 'foo.CSV': 'a;b\n3;4\n'},
            _limits(),
            'duplicate output member names',
        ),
        (
            {'dir\\file.csv': 'a;b\n1;2\n', 'dir/file.csv': 'a;b\n3;4\n'},
            _limits(),
            'duplicate output member names',
        ),
        (
            {'dir/': b'', 'DIR': 'a;b\n1;2\n'},
            _limits(),
            'duplicate output member names',
        ),
        (
            {'dir': b'file payload', 'dir/file.csv': 'a;b\n1;2\n'},
            _limits(),
            'file ZIP member is an ancestor',
        ),
        (
            {'dir/file.csv': 'a;b\n1;2\n', 'dir': b'file payload'},
            _limits(),
            'file ZIP member is an ancestor',
        ),
        (
            {'large.csv': b'x' * 200},
            _limits(max_member_uncompressed_bytes=100),
            'member uncompressed size',
        ),
        (
            {'compressible.csv': b'x' * 10_000},
            _limits(max_compression_ratio=1.1),
            'compression ratio',
        ),
    ],
)
def test_zip_metadata_policy_rejects_unsafe_archives_before_consumption(
    tmp_path: Path,
    members: dict[str, str | bytes],
    limits: ArchiveSafetyLimits,
    reason: str,
) -> None:
    """Each unsafe central-directory condition fails before member reads."""
    archive_path = write_zip(tmp_path / 'unsafe.zip', members)

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(CorruptedZipError, match=reason),
    ):
        validate_zip_archive(archive_path, archive, limits=limits)


@pytest.mark.unit
@pytest.mark.parametrize(
    'member_name',
    [
        'dir/payload:secret.csv',
        'dir/CON.csv',
        'dir/PRN.csv',
        'dir/AUX.csv',
        'dir/NUL.csv',
        'dir/COM1.csv',
        'dir/COM9.csv',
        'dir/LPT1.csv',
        'dir/LPT9.csv',
        *[f'dir/{name}' for name in _RESERVED_WIN32_BASENAMES],
        'dir/file.csv.',
        'dir/file.csv ',
        'dir/file<bad.csv',
        'dir/file>bad.csv',
        'dir/file"bad.csv',
        'dir/file|bad.csv',
        'dir/file?bad.csv',
        'dir/file*bad.csv',
    ],
)
def test_zip_metadata_policy_rejects_win32_namespace_names(
    tmp_path: Path, member_name: str
) -> None:
    """ZIP components must be safe when materialized by Win32 consumers."""
    archive_path = write_zip(
        tmp_path / 'win32-names.zip',
        {member_name: 'a;b\n1;2\n'},
    )

    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(CorruptedZipError, match='unsafe Windows ZIP member'),
    ):
        validate_zip_archive(archive_path, archive, limits=_limits())


@pytest.mark.unit
@pytest.mark.parametrize(
    'name',
    [
        *_RESERVED_WIN32_BASENAMES,
        'report?.csv',
        'report<.csv',
        'report|.csv',
        'report.',
        'report ',
    ],
)
def test_portable_basename_validator_rejects_win32_namespace_names(
    name: str,
) -> None:
    """Shared basename rules cover names before source-specific translation."""
    with pytest.raises(ValueError):
        validate_portable_basename(name)


@pytest.mark.unit
def test_zip_metadata_policy_allows_directory_ancestor(
    tmp_path: Path,
) -> None:
    """A directory entry may legitimately contain a descendant member."""
    archive_path = write_zip(
        tmp_path / 'directory-ancestor.zip',
        {'dir/': b'', 'dir/file.csv': 'a;b\n1;2\n'},
    )

    with zipfile.ZipFile(archive_path) as archive:
        validated = validate_zip_archive(
            archive_path, archive, limits=_limits()
        )

    assert [info.filename for info in validated] == ['dir/', 'dir/file.csv']


@pytest.mark.unit
@pytest.mark.parametrize('kind', ['encrypted', 'symlink', 'special'])
def test_zip_metadata_policy_rejects_nonportable_member_types(
    tmp_path: Path, kind: str
) -> None:
    """Encrypted, symlink, and special entries never reach a consumer."""
    archive_path = tmp_path / 'metadata.zip'
    archive_path.write_bytes(b'placeholder')
    info = zipfile.ZipInfo('member.csv')
    info.file_size = 1
    info.compress_size = 1
    if kind == 'encrypted':
        info.flag_bits |= 0x1
    elif kind == 'symlink':
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
    else:
        info.external_attr = (stat.S_IFIFO | 0o644) << 16

    fake_archive = _MetadataOnlyZip(info)

    with pytest.raises(CorruptedZipError):
        validate_zip_archive(
            archive_path,
            cast(zipfile.ZipFile, fake_archive),
            limits=_limits(),
        )


@pytest.mark.unit
def test_real_byte_counter_rejects_a_stream_larger_than_its_metadata(
    tmp_path: Path,
) -> None:
    """A deceptive central directory cannot evade the actual-byte cap."""
    archive_path = tmp_path / 'deceptive.zip'
    archive_path.write_bytes(b'placeholder')
    info = zipfile.ZipInfo('member.csv')
    info.file_size = 1
    info.compress_size = 1
    fake_archive = _StreamingZip(info, b'abcdef')

    with (
        open_limited_zip_member(
            cast(zipfile.ZipFile, fake_archive),
            'member.csv',
            archive_path=archive_path,
            limits=_limits(
                max_member_uncompressed_bytes=3,
                max_total_uncompressed_bytes=3,
            ),
        ) as member,
        pytest.raises(CorruptedZipError, match='actual decompressed bytes'),
    ):
        member.read()


@pytest.mark.unit
def test_crc_validation_respects_an_explicit_empty_info_list(
    tmp_path: Path,
) -> None:
    """An already-filtered archive does not re-read its central directory."""
    archive_path = tmp_path / 'empty-selection.zip'
    archive_path.write_bytes(b'placeholder')

    class _InfolistSpy:
        def __init__(self) -> None:
            self.calls = 0

        def infolist(self) -> list[zipfile.ZipInfo]:
            self.calls += 1
            return []

    infolist_spy = _InfolistSpy()
    validate_zip_crc_with_limits(
        archive_path,
        cast(zipfile.ZipFile, infolist_spy),
        limits=_limits(),
        infos=[],
    )
    assert infolist_spy.calls == 0


class _MetadataOnlyZip:
    """Minimal central-directory collaborator for pure validation branches."""

    def __init__(self, info: zipfile.ZipInfo) -> None:
        self._info = info

    def infolist(self) -> list[zipfile.ZipInfo]:
        """Return the synthetic archive entry."""
        return [self._info]


class _StreamingZip:
    """Minimal ZIP collaborator whose data exceeds its declared metadata."""

    filename = 'synthetic.zip'

    def __init__(self, info: zipfile.ZipInfo, data: bytes) -> None:
        self._info = info
        self._data = data

    def getinfo(self, name: str) -> zipfile.ZipInfo:
        """Return the sole declared member when the name matches."""
        if name != self._info.filename:
            raise KeyError(name)
        return self._info

    def open(self, info: zipfile.ZipInfo, mode: str) -> io.BytesIO:
        """Return bytes that intentionally exceed the declared member size."""
        assert info is self._info
        assert mode == 'r'
        return io.BytesIO(self._data)


@pytest.mark.integration
def test_archive_safety_uses_fresh_local_default_when_limits_omitted(
    tmp_path: Path,
) -> None:
    """Functions use fresh local default limits without a global singleton."""
    import globaldatafinance.core.archive_safety as archive_safety_mod

    assert not hasattr(archive_safety_mod, 'get_archive_safety_limits')

    archive_path = write_zip(
        tmp_path / 'valid.zip', {'data.csv': 'col1;col2\nval1;val2\n'}
    )
    with zipfile.ZipFile(archive_path, 'r') as archive:
        infos = validate_zip_archive(archive_path, archive, limits=None)
        assert len(infos) == 1
        with open_limited_zip_member(
            archive, 'data.csv', archive_path=archive_path, limits=None
        ) as member:
            content = member.read()
            assert b'val1;val2' in content
