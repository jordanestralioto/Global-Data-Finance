"""Shared value objects and measurement primitives for ingestion benchmarks."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import threading
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast


class _MemoryInfo(Protocol):
    """The psutil memory fields used by the benchmark sampler."""

    rss: int


class _Process(Protocol):
    """The psutil process API used by the benchmark sampler."""

    def memory_info(self) -> _MemoryInfo: ...


class _VirtualMemory(Protocol):
    """The psutil virtual-memory field used in benchmark metadata."""

    available: int


class _PsutilModule(Protocol):
    """The narrow runtime psutil contract needed by this script."""

    Error: type[Exception]

    def Process(self) -> _Process: ...

    def virtual_memory(self) -> _VirtualMemory: ...


psutil = cast(_PsutilModule, importlib.import_module('psutil'))

MEBIBYTE = 1024**2
SCHEMA_VERSION = 1
SCENARIOS = (
    'import_root',
    'cvm',
    'cvm_text',
    'b3_100k',
    'b3_250k',
    'b3_annual',
    'runtime_footprint',
)
DEFAULT_ROWS = {
    'cvm': 269_181,
    'cvm_text': 8_000,
    'b3_100k': 100_000,
    'b3_250k': 250_000,
}


@dataclass(frozen=True)
class ScenarioInput:
    """One deterministic input and the facts needed to validate it."""

    scenario: str
    path: Path | None
    row_count: int
    input_sha256: str
    expected_first: str = ''
    expected_last: str = ''
    expected_digest: str = ''


class RssSampler:
    """Sample the current process RSS from a small background thread."""

    def __init__(self, interval_seconds: float = 0.01) -> None:
        """Create a sampler with the documented 10 ms default interval."""
        self.interval_seconds = interval_seconds
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.before_bytes = 0
        self.peak_bytes = 0

    def start(self) -> None:
        """Start collection before the measured product operation."""
        self.before_bytes = self._rss_bytes()
        self.peak_bytes = self.before_bytes
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        """Stop collection and return the final RSS measurement."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        final = self._rss_bytes()
        self.peak_bytes = max(self.peak_bytes, final)
        return final

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.peak_bytes = max(self.peak_bytes, self._rss_bytes())

    def _rss_bytes(self) -> int:
        try:
            return int(self._process.memory_info().rss)
        except psutil.Error:
            return self.peak_bytes


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest without retaining the input."""
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def directory_digest(path: Path) -> str:
    """Hash accepted external COTAHIST input names and bytes."""
    digest = hashlib.sha256()
    for child in sorted(path.glob('COTAHIST_A*'), key=lambda item: item.name):
        if child.is_file():
            digest.update(child.name.encode('utf-8'))
            digest.update(sha256_file(child).encode('ascii'))
    return digest.hexdigest()


def verify_input_digest(source: ScenarioInput) -> None:
    """Reject a source changed after the parent recorded its checksum."""
    if source.path is None or not source.input_sha256:
        return
    actual = (
        directory_digest(source.path)
        if source.path.is_dir()
        else sha256_file(source.path)
    )
    if actual != source.input_sha256:
        raise ValueError('Benchmark input checksum changed before measurement')


def schema_fingerprint(schema: Any) -> str:
    """Fingerprint an Arrow schema without depending on physical encoding."""
    return hashlib.sha256(schema.to_string().encode('utf-8')).hexdigest()


def logical_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """Hash typed logical rows without depending on Parquet encoding.

    The digest deliberately includes the Python value type and, for decimals,
    the exact ``Decimal.as_tuple()`` representation.  This catches changes to
    values, nulls, ordering, and decimal precision while keeping validation
    bounded to one row at a time.
    """
    digest = hashlib.sha256()
    for row in rows:
        canonical = {
            str(key): _canonical_value(value)
            for key, value in sorted(
                row.items(), key=lambda item: str(item[0])
            )
        }
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
            sort_keys=True,
        ).encode('utf-8')
        digest.update(encoded)
        digest.update(b'\n')
    return digest.hexdigest()


def digest_parquet_rows(
    parquet: Any,
    *,
    batch_size: int,
    boundary_column: str,
    columns: list[str] | None = None,
) -> tuple[str, str, str]:
    """Digest Arrow rows one at a time and retain boundary values."""
    first = ''
    last = ''

    def rows() -> Iterator[dict[str, Any]]:
        nonlocal first, last
        for batch in parquet.iter_batches(
            batch_size=batch_size, columns=columns
        ):
            names = batch.schema.names
            arrays = [batch.column(idx) for idx in range(batch.num_columns)]
            for r_idx in range(batch.num_rows):
                row = {
                    name: arrays[c_idx][r_idx].as_py()
                    for c_idx, name in enumerate(names)
                }
                val = row.get(boundary_column)
                text = '' if val is None else str(val)
                if not first:
                    first = text
                last = text
                yield row

    return logical_digest(rows()), first, last


def _canonical_value(value: Any) -> dict[str, Any]:
    """Represent one supported logical value with an explicit type tag."""
    if value is None:
        return {'type': 'null', 'value': None}
    if isinstance(value, Decimal):
        decimal_tuple = value.as_tuple()
        return {
            'type': 'decimal',
            'value': [
                decimal_tuple.sign,
                list(decimal_tuple.digits),
                decimal_tuple.exponent,
            ],
        }
    if isinstance(value, date):
        return {'type': 'date', 'value': value.isoformat()}
    if isinstance(value, bool):
        return {'type': 'bool', 'value': value}
    if isinstance(value, (int, float, str)):
        return {'type': type(value).__name__, 'value': value}
    raise TypeError(f'Unsupported benchmark logical value: {type(value)!r}')


def base_record(source: ScenarioInput, repeat_index: int) -> dict[str, Any]:
    """Build fields shared by successful and failed measurements."""
    return {
        'schema_version': SCHEMA_VERSION,
        'git_sha': os.environ.get('GDF_BENCHMARK_GIT_SHA', 'unknown'),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count() or 1,
        'available_memory_mib': int(
            psutil.virtual_memory().available // MEBIBYTE
        ),
        'timestamp': datetime.now(UTC).isoformat(),
        'scenario': source.scenario,
        'repeat_index': repeat_index,
        'input_sha256': source.input_sha256,
        'row_count': source.row_count,
    }


def unmeasured_record(
    source: ScenarioInput,
    repeat_index: int,
    *,
    status: str,
    reason: str,
    git_sha: str | None = None,
    elapsed_seconds: float = 0.0,
    rss_before_mib: float = 0.0,
    rss_peak_mib: float = 0.0,
    rss_after_mib: float = 0.0,
) -> dict[str, Any]:
    """Build a failed or skipped benchmark record with stable empty metrics."""
    record = base_record(source, repeat_index)
    if git_sha is not None:
        record['git_sha'] = git_sha
    phase_seconds = (
        {'operation': elapsed_seconds} if elapsed_seconds > 0.0 else {}
    )
    record.update(
        {
            'schema_fingerprint': '',
            'logical_digest': '',
            'logical_equivalence': False,
            'elapsed_seconds': elapsed_seconds,
            'phase_seconds': phase_seconds,
            'rss_before_mib': rss_before_mib,
            'rss_peak_mib': rss_peak_mib,
            'rss_after_mib': rss_after_mib,
            'output_bytes': 0,
            'status': status,
            'reason': reason,
        }
    )
    return record


def write_json(path: Path, payload: object) -> None:
    """Write one deterministic JSON payload for a parent to consume."""
    path.write_text(
        json.dumps(payload, sort_keys=True) + '\n', encoding='utf-8'
    )
