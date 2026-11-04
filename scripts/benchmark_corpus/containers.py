"""Deterministic container selection for synthetic annual B3 inputs."""

from __future__ import annotations

import zipfile
from pathlib import Path


def select_b3_container(path: Path, input_format: str) -> Path:
    """Keep TXT or replace it with exactly one reproducible ZIP input."""
    if input_format == 'txt':
        return path
    info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    output = path.with_suffix('.ZIP')
    with (
        zipfile.ZipFile(output, 'w') as archive,
        path.open('rb') as source,
        archive.open(info, 'w') as target,
    ):
        while chunk := source.read(64 * 1024):
            target.write(chunk)
    path.unlink()
    return output
