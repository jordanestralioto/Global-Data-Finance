"""Deterministic SHA-256 calculation for file contents."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash file contents in bounded 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
