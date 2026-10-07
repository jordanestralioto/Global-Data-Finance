"""Artifact schema, count, and typed-row validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.benchmark_corpus.synthetic import B3_SYNTHETIC_DIGEST_COLUMNS
from scripts.benchmark_support.digests import (
    digest_parquet_rows,
    schema_fingerprint,
)
from scripts.benchmark_support.models import ScenarioInput

_pq: Any = None


def _get_pq() -> Any:
    """Return ``pyarrow.parquet``, importing lazily on first call."""
    global _pq
    if _pq is None:
        import pyarrow.parquet as pq

        _pq = pq
    return _pq


def validate_cvm_output(
    output_dir: Path,
    source: ScenarioInput,
) -> tuple[int, str, bool, int, str]:
    """Validate a generated CVM artifact's typed logical rows and schema."""
    outputs = sorted(output_dir.glob('*.parquet'))
    if (
        len(outputs) != 1
        or (parquet := _get_pq().ParquetFile(outputs[0])).metadata is None
    ):
        return 0, '', False, 0, ''
    digest, first, last = digest_parquet_rows(
        parquet, batch_size=50_000, boundary_column='identificador'
    )
    row_count = parquet.metadata.num_rows
    valid = (
        row_count == source.row_count
        and (first, last) == (source.expected_first, source.expected_last)
        and b'pandas' not in (parquet.schema_arrow.metadata or {})
        and (not source.expected_digest or digest == source.expected_digest)
    )
    fp = schema_fingerprint(parquet.schema_arrow)
    return row_count, fp, valid, outputs[0].stat().st_size, digest


def validate_b3_output(
    output: Path,
    source: ScenarioInput,
) -> tuple[int, str, bool, int, str]:
    """Validate B3 schema, row order, count, and typed output."""
    if (parquet := _get_pq().ParquetFile(output)).metadata is None:
        return 0, '', False, 0, ''
    digest, first, last = digest_parquet_rows(
        parquet,
        batch_size=200_000,
        boundary_column='ticker',
        columns=(
            None
            if source.scenario == 'b3_annual'
            else list(B3_SYNTHETIC_DIGEST_COLUMNS)
        ),
    )
    import globaldatafinance.brazil.b3_data.historical_quotes as b3_quotes

    nr = parquet.metadata.num_rows
    exp_rows = nr == source.row_count if source.row_count else nr > 0
    schema = b3_quotes.parquet_writer.build_b3_schema()
    valid = (
        parquet.schema_arrow == schema
        and exp_rows
        and (not source.expected_first or first == source.expected_first)
        and (not source.expected_last or last == source.expected_last)
        and (source.row_count > 0 or bool(first and last))
        and bool(source.expected_digest)
        and digest == source.expected_digest
    )
    fp = schema_fingerprint(parquet.schema_arrow)
    return nr, fp, valid, output.stat().st_size, digest
