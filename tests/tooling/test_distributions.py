"""Distribution checks reject missing modules and inconsistent metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_distributions import REQUIRED_MODULES, inspect_distributions
from scripts.file_digests import sha256_file
from tests.support.release_fixtures import build_distributions

pytestmark = pytest.mark.integration


def test_both_distributions_contain_required_modules_and_matching_digests(
    tmp_path: Path,
) -> None:
    """Wheel and source metadata agree while hashes identify exact bytes."""
    wheel, source = build_distributions(tmp_path)

    reports = inspect_distributions(tmp_path, '0.2.0')

    assert {report['version'] for report in reports} == {'0.2.0'}
    assert {report['sha256'] for report in reports} == {
        sha256_file(wheel),
        sha256_file(source),
    }
    assert all(
        report['modules'] == list(REQUIRED_MODULES) for report in reports
    )


@pytest.mark.parametrize('module', REQUIRED_MODULES)
def test_distribution_without_implemented_safety_module_is_rejected(
    tmp_path: Path, module: str
) -> None:
    """Untracked safety implementations cannot silently disappear at build."""
    build_distributions(tmp_path, missing=module)

    with pytest.raises(ValueError, match='omits required module'):
        inspect_distributions(tmp_path, '0.2.0')


@pytest.mark.parametrize(
    'wheel_version,source_version,expected',
    [
        ('0.2.0', '0.1.5', '0.2.0'),
        ('0.2.0', '0.1.5', None),
        ('0.1.5.dev28', '0.1.5.dev28', '0.2.0'),
    ],
)
def test_tag_or_distribution_version_mismatch_blocks_release(
    tmp_path: Path,
    wheel_version: str,
    source_version: str,
    expected: str | None,
) -> None:
    """A development build cannot satisfy a stable release tag."""
    build_distributions(
        tmp_path, wheel_version=wheel_version, source_version=source_version
    )

    with pytest.raises(ValueError, match='version'):
        inspect_distributions(tmp_path, expected)


def test_missing_distribution_blocks_release(tmp_path: Path) -> None:
    """Both formats must be checked before the publish job can proceed."""
    wheel, _source = build_distributions(tmp_path)
    wheel.unlink()

    with pytest.raises(ValueError, match='exactly one wheel and sdist'):
        inspect_distributions(tmp_path)
