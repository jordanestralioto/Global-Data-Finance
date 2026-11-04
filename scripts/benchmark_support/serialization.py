"""Stable JSON serialization for benchmark child results."""

from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload: object) -> None:
    """Write one deterministic JSON payload for a parent to consume."""
    path.write_text(
        json.dumps(payload, sort_keys=True) + '\n', encoding='utf-8'
    )
