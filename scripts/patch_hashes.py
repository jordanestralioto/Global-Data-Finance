"""Calculate canonical SHA-256 hashes for unified Git patches."""

from __future__ import annotations

import hashlib


def file_patch_hashes(diff_text: str) -> dict[str, str]:
    """Return hashes for complete raw unified patches by file."""
    chunks: list[str] = []
    current: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith('diff --git '):
            if current:
                chunks.append(''.join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append(''.join(current))
    if not chunks and diff_text:
        chunks = [diff_text]

    hashes: dict[str, str] = {}
    for chunk in chunks:
        file_path = _patch_file_path(chunk)
        if file_path is not None:
            hashes[file_path] = hashlib.sha256(
                chunk.encode('utf-8')
            ).hexdigest()
    return hashes


def canonical_patch_sha256(diff_text: str, file_path: str) -> str | None:
    """Return the canonical hash for one file patch, if it is present."""
    return file_patch_hashes(diff_text).get(file_path)


def _patch_file_path(chunk: str) -> str | None:
    """Extract the post-change path, retaining deletion paths when needed."""
    for line in chunk.splitlines():
        if line.startswith('+++ b/'):
            return line[6:]
    for line in chunk.splitlines():
        if line.startswith('--- a/'):
            return line[6:]
    return None
