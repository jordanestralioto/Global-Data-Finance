"""Deterministic tests for shared real-validation helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.real_validation_utils import (
    failed_details,
    is_external_message,
    sha256_file,
    temporary_paths,
)

pytestmark = pytest.mark.unit


def test_failed_details_preserves_public_result() -> None:
    """A validation failure retains the public boundary evidence."""
    result = failed_details({'success': False}, 'bad result')

    assert result == {
        'status': 'failed',
        'message': 'bad result',
        'publicResult': {'success': False},
        'published': True,
    }


@pytest.mark.parametrize(
    ('message', 'expected'),
    [
        ('DNS lookup failed', True),
        ('request timeout', True),
        ('connection refused', True),
        ('invalid parquet schema', False),
    ],
)
def test_external_message_classifier_is_explicit(
    message: str, expected: bool
) -> None:
    """Only network-shaped public errors become external failures."""
    assert is_external_message(message) is expected


def test_temporary_paths_are_sorted_and_missing_roots_are_empty(
    tmp_path: Path,
) -> None:
    """Evidence reports all known staging markers below the workspace."""
    (tmp_path / 'z-recovery').mkdir()
    (tmp_path / 'a.tmp').touch()
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'preflight.zip').touch()

    assert temporary_paths(tmp_path) == [
        'a.tmp',
        'nested/preflight.zip',
        'z-recovery',
    ]
    assert temporary_paths(tmp_path / 'missing') == []


def test_sha256_file_hashes_binary_content_in_chunks(tmp_path: Path) -> None:
    """Input evidence uses the canonical SHA-256 digest."""
    path = tmp_path / 'input.bin'
    path.write_bytes(b'abc')

    assert sha256_file(path) == hashlib.sha256(b'abc').hexdigest()
