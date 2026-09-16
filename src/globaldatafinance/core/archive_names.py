"""Canonical and safe member names for ZIP extraction boundaries."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from ..macro_exceptions import CorruptedZipError

_INVALID_WIN32_CHARS = frozenset('<>:"|?*')
_RESERVED_WIN32_DEVICE_NAMES = frozenset(
    {'aux', 'con', 'conin$', 'conout$', 'nul', 'prn'}
)
_RESERVED_WIN32_DEVICE_PREFIXES = frozenset({'com', 'lpt'})
_RESERVED_WIN32_DEVICE_SUFFIXES = frozenset('123456789¹²³')


def validate_portable_basename(name: str) -> str:
    """Validate one basename against POSIX and Win32 naming rules.

    The validator is deliberately independent of an archive or download
    exception type. Callers at different boundaries can translate the
    resulting ``ValueError`` into their own diagnostic contract.
    """
    if not isinstance(name, str) or not name:
        raise ValueError('basename is empty or is not a string')
    if name in {'.', '..'}:
        raise ValueError('basename cannot be a dot path component')
    if (
        any(ord(character) < 32 for character in name)
        or any(character in _INVALID_WIN32_CHARS for character in name)
        or '/' in name
        or '\\' in name
    ):
        raise ValueError(
            'basename contains invalid or path-separator characters'
        )
    if name.endswith((' ', '.')):
        raise ValueError('basename cannot end with a space or dot')

    windows_path = PureWindowsPath(name)
    if windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise ValueError(
            'basename cannot be an absolute or drive-qualified path'
        )
    if len(windows_path.parts) != 1:
        raise ValueError('basename cannot contain path components')

    canonical = name.rstrip(' .').casefold()
    stem = canonical.split('.', maxsplit=1)[0].rstrip(' .')
    if stem in _RESERVED_WIN32_DEVICE_NAMES or _is_numbered_dos_device(stem):
        raise ValueError('basename is reserved by the Win32 device namespace')
    return name


def canonicalize_archive_member_name(
    archive_path: Path, member_name: str
) -> str:
    """Validate a member and return its destination-safe canonical name."""
    if not member_name or '\x00' in member_name:
        _reject(archive_path, 'member name is empty or invalid')

    windows_view = PureWindowsPath(member_name)
    normalized_separators = member_name.replace('\\', '/')
    posix_view = PurePosixPath(normalized_separators)
    if (
        posix_view.is_absolute()
        or windows_view.is_absolute()
        or windows_view.drive
        or '..' in posix_view.parts
    ):
        _reject(archive_path, f'unsafe ZIP member path: {member_name!r}')

    components = [part for part in normalized_separators.split('/') if part]
    if not components:
        _reject(archive_path, f'unsafe ZIP member path: {member_name!r}')
    for component in components:
        try:
            validate_portable_basename(component)
        except ValueError as error:
            _reject(
                archive_path,
                f'unsafe Windows ZIP member name: {member_name!r} ({error})',
            )

    return '/'.join(
        component.rstrip(' .').casefold() for component in components
    )


def _is_numbered_dos_device(stem: str) -> bool:
    """Return whether a stem names a numbered Win32 device."""
    if len(stem) != 4 or stem[:3] not in _RESERVED_WIN32_DEVICE_PREFIXES:
        return False
    return stem[3] in _RESERVED_WIN32_DEVICE_SUFFIXES


def _reject(archive_path: Path, reason: str) -> None:
    """Raise the common archive-rejection exception."""
    raise CorruptedZipError(str(archive_path), reason)
