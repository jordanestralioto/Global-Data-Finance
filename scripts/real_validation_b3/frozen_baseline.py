"""Validate frozen COTAHIST input evidence and row fingerprints."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from ..cotahist_oracle import OracleMismatch
from ..real_validation_types import ValidationCase
from ..real_validation_utils import sha256_file
from .artifact_validation import _BATCH_SIZE

_FROZEN_CORPUS_FIRST_YEAR = 2000

_FROZEN_CORPUS_LAST_YEAR = 2026

_FROZEN_BASELINE = {
    'rawQuotes': 22_305_860,
    'previousSupportedRows': 22_303_577,
    'blockLotRowsByYear': {2023: 30, 2024: 346, 2025: 539, 2026: 1_368},
    'blockLotDistinctTradingCodes': 345,
    'blockLotVolumeTotal': '57359085637.97',
    'lastTradingDate': '2026-09-02',
}


def _case_source_paths(case: ValidationCase) -> tuple[Path, ...]:
    if case.input_files:
        paths = tuple(
            Path(item.path).expanduser().resolve() for item in case.input_files
        )
        if paths != tuple(sorted(paths, key=_source_sort_key)):
            raise ValueError(
                'COTAHIST case inputFiles are not in source order'
            )
        for path, snapshot in zip(paths, case.input_files, strict=True):
            if path.name != Path(snapshot.path).name:
                raise ValueError(
                    'COTAHIST case input identity is inconsistent'
                )
            if path.stat().st_size != snapshot.size_bytes:
                raise ValueError(f'COTAHIST input size changed: {path.name}')
            if sha256_file(path) != snapshot.sha256:
                raise ValueError(
                    f'COTAHIST input checksum changed: {path.name}'
                )
        return paths
    return (Path(case.input_path).expanduser().resolve(),)


def _expected_frozen_checksums(
    source_paths: Sequence[Path],
    *,
    enabled: bool = False,
) -> dict[str, str] | None:
    if not enabled:
        return None
    years = sorted(_path_year(path) for path in source_paths)
    if years != list(
        range(_FROZEN_CORPUS_FIRST_YEAR, _FROZEN_CORPUS_LAST_YEAR + 1)
    ):
        raise ValueError(
            'Historical COTAHIST baseline requires the complete '
            '2000-2026 range'
        )
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / 'docs'
        / 'reference'
        / 'cotahist-v2-supplied-corpus.sha256'
    )
    expected: dict[str, str] = {}
    for line in manifest_path.read_text(encoding='ascii').splitlines():
        digest, filename = line.split(maxsplit=1)
        expected[filename.strip()] = digest
    return expected


def _validate_frozen_baseline(details: Mapping[str, Any]) -> None:
    for key, expected in _FROZEN_BASELINE.items():
        if details.get(key) != expected:
            raise OracleMismatch(
                f'frozen corpus acceptance mismatch for {key}: '
                f'expected={expected!r}, observed={details.get(key)!r}'
            )
    if details.get('intentionalExclusions') != 0:
        raise OracleMismatch('complete frozen extraction has exclusions')
    if details.get('previousTwentyFieldsEqual') is not True:
        raise OracleMismatch('the previously supported 20 fields changed')


def _ordered_rows_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=_BATCH_SIZE):
        for row in batch.to_pylist():
            encoded = json.dumps(
                row,
                default=str,
                ensure_ascii=True,
                sort_keys=False,
                separators=(',', ':'),
            ).encode('utf-8')
            digest.update(len(encoded).to_bytes(8, 'big'))
            digest.update(encoded)
    return digest.hexdigest()


def _source_sort_key(path: Path) -> tuple[int, str, str]:
    return _path_year(path), path.name.casefold(), path.name


def _path_year(path: Path) -> int:
    match = re.fullmatch(
        r'COTAHIST_A([0-9]{4})\.(?:ZIP|TXT)', path.name, flags=re.I
    )
    if match is None:
        raise ValueError(f'invalid COTAHIST annual filename: {path.name}')
    return int(match.group(1))
