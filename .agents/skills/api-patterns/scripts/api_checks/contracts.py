"""Evidence types shared by the standalone API triage tool."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict


class FileResult(TypedDict):
    file: str
    type: str
    analysis: str
    passed: list[str]
    issues: list[str]
    unverified: list[str]


def file_result(path: Path, kind: str, analysis: str) -> FileResult:
    return {
        'file': str(path),
        'type': kind,
        'analysis': analysis,
        'passed': [],
        'issues': [],
        'unverified': [],
    }


def has_pattern(content: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, content, re.I) for pattern in patterns)
