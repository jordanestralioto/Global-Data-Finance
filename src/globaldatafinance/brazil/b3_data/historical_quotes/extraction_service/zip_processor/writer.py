"""Create Parquet writer sessions for decoded B3 rows."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from ...cotahist_parser import CsvRow
from ...parquet_writer.schema import build_b3_schema, schema_fingerprint
from ...parquet_writer.session import B3ParquetWriterSession


def write_csv_rows(
    session: B3ParquetWriterSession | None,
    rows: list[CsvRow],
    temp_output: Path,
    schema_metadata: dict[bytes, bytes] | None,
    *,
    batch_observer: Callable[[Any], None] | None = None,
) -> tuple[B3ParquetWriterSession, str]:
    """Write strict parser rows without a typed-dictionary round trip."""
    session, fingerprint = session_for_write(
        session, temp_output, schema_metadata
    )
    try:
        session.write_csv_rows(rows, batch_observer=batch_observer)
    except BaseException:
        with suppress(Exception):
            session.close()
        raise
    return session, fingerprint


def session_for_write(
    session: B3ParquetWriterSession | None,
    temp_output: Path,
    schema_metadata: dict[bytes, bytes] | None,
) -> tuple[B3ParquetWriterSession, str]:
    """Create or validate the one lazy Arrow session for a source."""
    if session is None:
        schema = build_b3_schema(metadata=schema_metadata)
        session = B3ParquetWriterSession().open(temp_output, schema)
        fingerprint = schema_fingerprint(schema)
    else:
        if session.schema is None:
            raise RuntimeError('B3 writer session lost its schema')
        fingerprint = schema_fingerprint(session.schema)
    return session, fingerprint
