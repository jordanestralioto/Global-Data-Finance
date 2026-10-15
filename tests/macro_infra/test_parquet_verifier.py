"""Persistent Parquet readback remains independent of transaction forks."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tests.support.parquet_verifier import ParquetVerifier
from tests.support.publication_crashes import ARTIFACT_NAMES

pytestmark = pytest.mark.integration


def test_parquet_verifier_reuses_its_process_and_rejects_corruption(
    tmp_path: Path,
) -> None:
    """Check actual rows/schema and reuse the process after corrupt input."""
    with ParquetVerifier() as verifier:
        pid = verifier.process.pid
        for version, rows in [('old', 1), ('new', 2)]:
            for name in ARTIFACT_NAMES:
                pq.write_table(
                    pa.table(
                        {'version': [version] * rows, 'item': [name] * rows}
                    ),
                    tmp_path / name,
                )
            verifier.verify(tmp_path)
            assert verifier.process.pid == pid
        path = tmp_path / ARTIFACT_NAMES[0]
        original = path.read_bytes()
        path.write_bytes(b'invalid Parquet')
        with pytest.raises(AssertionError, match='Parquet readback failed'):
            verifier.verify(tmp_path)
        path.write_bytes(original)
        verifier.verify(tmp_path)
    assert verifier.exit_code == 0
    assert verifier.connection.closed
