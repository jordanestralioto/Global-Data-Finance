"""Pure path-policy regressions shared by B3 and CVM entrypoints."""

import sys
from pathlib import Path

import pytest

from globaldatafinance.core.utils import assert_path_not_sensitive
from globaldatafinance.macro_exceptions import SecurityError

pytestmark = pytest.mark.unit


def _path_policy_allows(resolved: Path, raw: str) -> bool:
    """Return whether the public path policy accepts one candidate."""
    try:
        assert_path_not_sensitive(resolved, raw)
    except SecurityError:
        return False
    return True


@pytest.mark.parametrize(
    ('resolved', 'raw'),
    [
        (Path('/'), '/'),
        (Path('/private/etc/output'), '/private/etc/output'),
        (Path('/bin/output'), '/bin/output'),
        (Path('/sbin/output'), '/sbin/output'),
        (Path('/lib64/output'), '/lib64/output'),
        (Path('safe-output/windows'), 'D:\\'),
        (Path('safe-output/windows'), r'D:\Windows\System32'),
        (Path('safe-output/windows'), r'c:/WINDOWS/System32'),
        (Path('safe-output/windows'), r'E:\Program Files\Application'),
        (Path('safe-output/windows'), r'C:/Program Files/Application'),
        (Path('safe-output/windows'), r'F:\Program Files (x86)\Application'),
        (Path('safe-output/unc'), r'\\server\share\output'),
        (Path('safe-output/unc'), r'\\server\C$\output'),
        (Path('safe-output/unc'), r'\\server\share\trusted\..\outside'),
        (Path('safe-output/unc'), r'//SERVER/SHARE/TRUSTED/../outside'),
        (
            Path('safe-output/unc'),
            r'\\server\share\trusted\reports\..\..\outside',
        ),
        (
            Path('safe-output/unc'),
            r'//SERVER/SHARE/TRUSTED/reports/../../outside',
        ),
        (Path('safe-output/windows'), r'C:..\Windows\System32'),
        (Path('safe-output/windows'), r'C:Windows\System32'),
        (Path('safe-output/windows'), r'\Windows\System32'),
        (Path('safe-output/windows'), r'D:Program Files\App'),
        (Path('safe-output/windows'), r'd:Program Files/App'),
        (Path('safe-output/windows'), '/Windows/System32'),
    ],
)
def test_path_policy_rejects_privileged_roots_and_untrusted_windows_paths(
    resolved: Path, raw: str
) -> None:
    """Unsafe POSIX, drive, system, and UNC targets fail before writes."""
    with pytest.raises(SecurityError):
        assert_path_not_sensitive(resolved, raw)


@pytest.mark.parametrize(
    ('resolved', 'raw'),
    [
        (Path('/etc_backup'), '/etc_backup'),
        (Path('/private/etc_backup'), '/private/etc_backup'),
        (Path('/private/tmp/output'), '/private/tmp/output'),
        (Path('/private/var/folders/output'), '/private/var/folders/output'),
        (Path('safe-output/data'), r'D:\Data\output'),
        (Path('safe-output/data'), r'E:\Windows_backup\output'),
    ],
)
def test_path_policy_keeps_near_misses_valid(resolved: Path, raw: str) -> None:
    """Path-aware checks do not treat safe names as blocked prefixes."""
    assert _path_policy_allows(resolved, raw)


def test_path_policy_rejects_forward_slash_windows_system_root() -> None:
    """A slash-rooted Windows system path fails even on a POSIX host."""
    with pytest.raises(SecurityError):
        assert_path_not_sensitive(
            Path('/Windows/System32'), '/Windows/System32'
        )


def test_path_policy_rejects_macos_configuration_alias() -> None:
    """The native macOS /etc alias remains protected after resolution."""
    root = (
        Path('/etc').resolve()
        if sys.platform == 'darwin'
        else Path('/private/etc')
    )
    with pytest.raises(SecurityError):
        assert_path_not_sensitive(root / 'output', '/etc/output')


def test_path_policy_allows_only_descendants_of_configured_unc_roots() -> None:
    """An explicit UNC root permits only itself and its descendants."""
    trusted_root = r'\\fileserver\finance\trusted'

    assert_path_not_sensitive(
        Path('safe-output/unc'),
        r'//FILESERVER/FINANCE/TRUSTED/reports',
        allowed_unc_roots=[r'//fileserver/finance/trusted'],
    )
    with pytest.raises(SecurityError):
        assert_path_not_sensitive(
            Path('safe-output/unc'),
            r'\\fileserver\finance\other',
            allowed_unc_roots=[trusted_root],
        )

    with pytest.raises(SecurityError):
        assert_path_not_sensitive(
            Path('safe-output/unc'),
            r'\\fileserver\finance\trusted\..\outside',
            allowed_unc_roots=[trusted_root],
        )


def test_path_policy_uses_fresh_settings_when_allowed_unc_roots_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When allowed_unc_roots is omitted, fresh PathSafetySettings is used."""
    monkeypatch.setenv(
        'DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS',
        '["\\\\\\\\fileserver\\\\finance\\\\trusted"]',
    )
    assert _path_policy_allows(
        Path('safe-output/unc'),
        r'\\fileserver\finance\trusted\reports',
    )
    assert not _path_policy_allows(
        Path('safe-output/unc'),
        r'\\fileserver\finance\untrusted\reports',
    )
