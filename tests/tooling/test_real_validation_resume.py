"""Deterministic tests for manifest resume validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.real_validation_report import ReportFormatError, write_json
from scripts.real_validation_resume import resume_cases

pytestmark = pytest.mark.unit


def test_resume_rejects_unsupported_manifest_version(tmp_path: Path) -> None:
    """Resume fails closed when the persisted schema is not supported."""
    report_path = tmp_path / 'report'
    report_path.mkdir()
    write_json(
        report_path / 'manifest.json',
        {'schemaVersion': 999, 'cases': []},
    )

    with pytest.raises(
        ReportFormatError, match='unsupported real-validation manifest version'
    ):
        resume_cases(report_path, hash_file=lambda _path: '')
