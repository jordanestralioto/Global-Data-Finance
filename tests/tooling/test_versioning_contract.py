"""Tests for the Git-tag-derived distribution versioning contract."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
PYPROJECT_PATH = REPOSITORY_ROOT / 'pyproject.toml'


pytestmark = pytest.mark.unit


def _load_project_configuration() -> dict[str, Any]:
    """Load the project metadata used by the distribution build."""
    with PYPROJECT_PATH.open('rb') as file_handle:
        return tomllib.load(file_handle)


def test_distribution_version_is_derived_from_git_tags() -> None:
    """The build must derive version metadata without a static fallback."""
    configuration = _load_project_configuration()
    project = configuration['project']
    build_system = configuration['build-system']
    version_source = configuration['tool']['hatch']['version']
    raw_version_options = version_source['raw-options']
    cache_keys = configuration['tool']['uv']['cache-keys']

    assert 'version' not in project
    assert project['dynamic'] == ['version']
    assert 'hatch-vcs' in build_system['requires']
    assert version_source['source'] == 'vcs'
    assert version_source['tag-pattern'] == '^v(?P<version>.+)$'
    assert raw_version_options == {'local_scheme': 'no-local-version'}
    assert cache_keys == [
        {'file': 'pyproject.toml'},
        {'git': {'commit': True, 'tags': True}},
    ]
