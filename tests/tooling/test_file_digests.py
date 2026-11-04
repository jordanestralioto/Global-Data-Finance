"""Deterministic tests for the shared file digests module."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.file_digests import sha256_file

pytestmark = pytest.mark.unit


def test_sha256_file_matches_hashlib_and_handles_large_inputs(
    tmp_path: Path,
) -> None:
    """Bounded chunked hashing matches hashlib on empty and large files."""
    empty_file = tmp_path / 'empty.bin'
    empty_file.write_bytes(b'')
    assert sha256_file(empty_file) == hashlib.sha256(b'').hexdigest()

    small_file = tmp_path / 'small.bin'
    small_file.write_bytes(b'abc')
    assert sha256_file(small_file) == hashlib.sha256(b'abc').hexdigest()

    # Multi-megabyte file to prove chunked streaming across boundaries (>1 MiB)
    large_payload = b'x' * (1024 * 1024 + 42)
    large_file = tmp_path / 'large.bin'
    large_file.write_bytes(large_payload)
    assert sha256_file(large_file) == hashlib.sha256(large_payload).hexdigest()


def test_sha256_file_propagates_missing_file_error(tmp_path: Path) -> None:
    """File I/O exceptions are propagated without being swallowed."""
    missing_file = tmp_path / 'does_not_exist.bin'
    with pytest.raises(FileNotFoundError):
        sha256_file(missing_file)
