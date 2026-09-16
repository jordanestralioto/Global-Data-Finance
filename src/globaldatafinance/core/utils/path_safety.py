r"""Caller-destination safety policy shared by B3 and CVM entry points.

The policy rejects privileged POSIX directories, filesystem and drive roots,
protected Windows directories on every drive, and UNC paths unless they are
explicitly trusted. It is a defense for destinations provided by a caller; it
does not claim to constrain a caller that already has the process privileges.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PureWindowsPath

from ...macro_exceptions import SecurityError
from ..config import PathSafetySettings

_SENSITIVE_SYSTEM_DIRS: tuple[Path, ...] = (
    Path('/etc'),
    Path('/root'),
    Path('/sys'),
    Path('/proc'),
    Path('/dev'),
    Path('/boot'),
    Path('/usr'),
    Path('/var'),
    Path('/lib'),
)

_USER_SECRET_DIRNAMES: tuple[str, ...] = ('.ssh', '.aws', '.gnupg')

_SENSITIVE_WINDOWS_DIR_NAMES: tuple[str, ...] = (
    'Windows',
    'Program Files',
    'Program Files (x86)',
)


def _has_windows_drive(raw: str) -> bool:
    """True if ``raw`` looks like a Windows drive-letter path."""
    return len(raw) >= 2 and raw[1] == ':' and raw[0].isalpha()


def _is_unc_path(path: PureWindowsPath) -> bool:
    """Return whether a Windows path targets a network share."""
    return path.drive.startswith('\\\\')


def _is_drive_root(path: PureWindowsPath) -> bool:
    """Return whether a Windows path is exactly a drive root."""
    return bool(path.drive and path.root and len(path.parts) == 1)


def _is_administrative_unc_share(path: PureWindowsPath) -> bool:
    """Return whether a UNC path addresses an administrative share."""
    if not _is_unc_path(path):
        return False
    share_name = path.drive.rsplit('\\', maxsplit=1)[-1].rstrip(' .')
    return share_name.endswith('$')


def _is_below_windows_system_directory(path: PureWindowsPath) -> bool:
    """Return whether a drive path is below a protected Windows directory."""
    if not path.drive or _is_unc_path(path) or not path.root:
        return False
    components = _canonical_windows_components(path)
    protected_names = {
        directory_name.casefold().rstrip(' .')
        for directory_name in _SENSITIVE_WINDOWS_DIR_NAMES
    }
    return bool(components and components[0] in protected_names)


def _is_allowed_unc_destination(
    path: PureWindowsPath,
    allowed_unc_roots: Sequence[str],
) -> bool:
    """Return whether a UNC path is equal to or below a trusted root."""
    candidate_components = _canonical_unc_components(path)
    if candidate_components is None:
        return False

    for root in allowed_unc_roots:
        root_path = PureWindowsPath(root)
        root_components = _canonical_unc_components(root_path)
        if root_components is not None and _is_component_prefix(
            root_components, candidate_components
        ):
            return True
    return False


def _windows_relative_components(path: PureWindowsPath) -> tuple[str, ...]:
    """Return Windows path components without its drive or root anchor."""
    if path.anchor:
        return path.parts[1:]
    return path.parts


def _canonical_windows_component(component: str) -> str:
    """Normalize case and Win32-insignificant trailing punctuation."""
    return component.rstrip(' .').casefold()


def _canonical_windows_components(
    path: PureWindowsPath,
) -> tuple[str, ...]:
    """Return canonical non-anchor components for a Windows path."""
    return tuple(
        _canonical_windows_component(component)
        for component in _windows_relative_components(path)
        if component not in {'', '.'}
    )


def _canonical_unc_components(
    path: PureWindowsPath,
) -> tuple[str, ...] | None:
    """Return canonical server/share/path components for an absolute UNC."""
    if not _is_unc_path(path) or not path.is_absolute():
        return None
    if '..' in _windows_relative_components(path):
        return None

    server_share = path.drive.lstrip('\\').split('\\')
    components = [*server_share, *_windows_relative_components(path)]
    canonical = tuple(
        _canonical_windows_component(component)
        for component in components
        if component not in {'', '.'}
    )
    if len(canonical) < 2 or any(not component for component in canonical):
        return None
    return canonical


def _is_component_prefix(
    prefix: tuple[str, ...], candidate: tuple[str, ...]
) -> bool:
    """Return whether canonical components stay below an allowlist root."""
    return len(candidate) >= len(prefix) and candidate[: len(prefix)] == prefix


def _reject_windows_parent_components(
    path: PureWindowsPath, candidate_str: str
) -> None:
    """Reject explicit parent components before any path comparison."""
    if '..' in _windows_relative_components(path):
        raise SecurityError(
            'Parent components are denied for Windows caller destinations',
            path=candidate_str,
        )


def _is_root_relative_windows_path(
    candidate_str: str,
    path: PureWindowsPath,
) -> bool:
    """Return whether a root-relative Windows path has no drive or share."""
    if path.drive or path.root != '\\':
        return False
    if candidate_str.startswith('\\'):
        return not candidate_str.startswith('\\\\')
    if not candidate_str.startswith('/'):
        return False
    components = _canonical_windows_components(path)
    protected_names = {
        directory_name.casefold().rstrip(' .')
        for directory_name in _SENSITIVE_WINDOWS_DIR_NAMES
    }
    return bool(components and components[0] in protected_names)


def assert_path_not_sensitive(
    path: Path,
    raw_input: str | None = None,
    *,
    allowed_unc_roots: Sequence[str] | None = None,
) -> None:
    r"""Raise :class:`SecurityError` for an unsafe caller destination.

    Args:
        path: Resolved POSIX-native path. The path is used for filesystem
            root, system directory, and user-secret directory checks.
        raw_input: Original caller string, used to retain Windows and UNC
            semantics even when the library runs on a POSIX host.
        allowed_unc_roots: Explicit trusted UNC roots for this check. When
            omitted, values from ``DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS``
            are used.

    Raises:
        SecurityError: If the destination violates the caller-destination
            policy before any directory creation or output write occurs.
    """
    _assert_posix_path_not_sensitive(path)
    candidate_str = raw_input if raw_input is not None else str(path)
    _assert_windows_path_not_sensitive(candidate_str, allowed_unc_roots)


def _assert_posix_path_not_sensitive(path: Path) -> None:
    """Reject filesystem, system, and user-secret POSIX destinations."""
    if path == Path('/'):
        raise SecurityError(
            'Access to filesystem root is denied for caller destinations',
            path=str(path),
        )

    for posix_sensitive in _SENSITIVE_SYSTEM_DIRS:
        if path.is_relative_to(posix_sensitive):
            raise SecurityError(
                f"Access to sensitive system directory denied: '{path}' "
                f"is within protected path '{posix_sensitive}'",
                path=str(path),
            )

    home = Path.home()
    for secret_name in _USER_SECRET_DIRNAMES:
        secret_dir = home / secret_name
        if path.is_relative_to(secret_dir):
            raise SecurityError(
                f"Access to sensitive user directory denied: '{path}' "
                f"is within protected path '{secret_dir}'",
                path=str(path),
            )


def _assert_windows_path_not_sensitive(
    candidate_str: str,
    allowed_unc_roots: Sequence[str] | None,
) -> None:
    """Reject protected drive and untrusted UNC caller destinations."""
    windows_path = PureWindowsPath(candidate_str)
    if _has_windows_drive(candidate_str):
        if not windows_path.root:
            raise SecurityError(
                'Drive-relative Windows paths are denied for caller '
                'destinations',
                path=candidate_str,
            )
        _reject_windows_parent_components(windows_path, candidate_str)
        _assert_windows_drive_path_is_safe(windows_path, candidate_str)
        return

    if _is_root_relative_windows_path(candidate_str, windows_path):
        raise SecurityError(
            'Root-relative Windows paths are denied for caller destinations',
            path=candidate_str,
        )

    if not _is_unc_path(windows_path):
        return
    _reject_windows_parent_components(windows_path, candidate_str)
    if _is_administrative_unc_share(windows_path):
        raise SecurityError(
            'Administrative UNC shares are denied for caller destinations',
            path=candidate_str,
        )
    configured_roots = PathSafetySettings.resolve_allowed_unc_roots(
        allowed_unc_roots
    )
    if not _is_allowed_unc_destination(windows_path, configured_roots):
        raise SecurityError(
            'UNC destination is not under an explicitly trusted root',
            path=candidate_str,
        )


def _assert_windows_drive_path_is_safe(
    path: PureWindowsPath, candidate_str: str
) -> None:
    """Reject drive roots and protected directories across drive letters."""
    if _is_drive_root(path):
        raise SecurityError(
            'Access to a Windows drive root is denied for caller destinations',
            path=candidate_str,
        )
    if _is_below_windows_system_directory(path):
        raise SecurityError(
            'Access to sensitive Windows directory denied: '
            f"'{candidate_str}' is within a protected directory",
            path=candidate_str,
        )
