"""Benchmark scenarios and immutable input descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 2

SCENARIOS = (
    'import_root',
    'cvm',
    'cvm_text',
    'b3_100k',
    'b3_250k',
    'b3_multi_4x25k',
    'b3_annual',
    'runtime_footprint',
)

DEFAULT_ROWS = {
    'cvm': 269_181,
    'cvm_text': 8_000,
    'b3_100k': 100_000,
    'b3_250k': 250_000,
    'b3_multi_4x25k': 100_000,
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
    executor_backend: str = 'thread'
    processing_mode: str = 'fast'
    source_count: int = 1
    worker_limit: int = 1
