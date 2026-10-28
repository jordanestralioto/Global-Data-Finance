"""Ordered streaming merge for transaction-private B3 Parquet artifacts."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .....macro_exceptions import ExtractionError, ParquetWriteError
from ..async_execution import check_phase_cancellation
from ..parquet_writer.metadata_verification import open_verified_parquet
from ..parquet_writer.session import ROW_GROUP_LIMIT, B3ParquetWriterSession

if TYPE_CHECKING:
    from pyarrow import Schema


def merge_temp_files_streaming(
    temp_files: Sequence[Path],
    final_output: Path,
    expected_schema: Schema,
    expected_rows: Sequence[int] | None = None,
) -> int:
    """Merge valid temporary files in input order without deleting sources.

    ``expected_rows`` carries the counts established by each source worker.
    When supplied, the merge validates those counts against the temporary
    Parquet metadata before copying any batches, preventing a mutated or
    truncated private artifact from being published under a valid schema.
    """
    _validate_merge_inputs(temp_files, expected_rows)

    session = B3ParquetWriterSession().open(final_output, expected_schema)
    try:
        for index, temp_file in enumerate(temp_files):
            source = _open_validated_temporary(
                temp_file,
                expected_schema,
                None if expected_rows is None else expected_rows[index],
            )
            try:
                _copy_source_batches(session, source, temp_file)
            finally:
                source.close()
        session.close()
        return session.rows_written
    except Exception as error:
        with contextlib.suppress(Exception):
            session.close()
        with contextlib.suppress(OSError):
            final_output.unlink(missing_ok=True)
        if isinstance(error, ExtractionError):
            raise
        raise ParquetWriteError(
            str(final_output), f'B3 streaming merge failed: {error}'
        ) from error
    finally:
        with contextlib.suppress(Exception):
            session.close()


def _validate_temporary_row_count(
    temp_file: Path,
    observed_rows: int,
    expected_rows: int | None,
) -> None:
    """Reject a private artifact whose metadata disagrees with its source."""
    if expected_rows is None or observed_rows == expected_rows:
        return
    raise ExtractionError(
        str(temp_file),
        'B3 temporary Parquet row count is incompatible: '
        f'expected {expected_rows}, observed {observed_rows}',
    )


def _cancellable_batches(source: Any) -> Iterator[Any]:
    for batch in source.iter_batches(batch_size=ROW_GROUP_LIMIT):
        check_phase_cancellation()
        yield batch


def _copy_source_batches(
    session: B3ParquetWriterSession, source: Any, path: Path
) -> None:
    """Check consumed source rows independently of the writer's flushes."""
    consumed = 0
    for batch in _cancellable_batches(source):
        consumed += batch.num_rows
        session.write_batches((batch,))
    expected = source.metadata.num_rows
    if consumed != expected:
        raise ExtractionError(
            str(path),
            'B3 merge consumed row count is incompatible: '
            f'expected {expected}, observed {consumed}',
        )


def _validate_merge_inputs(
    temp_files: Sequence[Path], expected_rows: Sequence[int] | None
) -> None:
    """Reject structurally inconsistent merge metadata before I/O."""
    if expected_rows is not None and (
        len(expected_rows) != len(temp_files)
        or any(rows < 0 for rows in expected_rows)
    ):
        raise ValueError(
            'expected_rows must match temp_files and contain '
            'non-negative values'
        )


def _open_validated_temporary(
    temp_file: Path,
    expected_schema: Schema,
    expected_rows: int | None,
) -> Any:
    """Open a private source artifact only after its invariants hold."""
    if not temp_file.is_file():
        raise ExtractionError(
            str(temp_file), 'B3 temporary Parquet artifact is missing'
        )
    source, _ = open_verified_parquet(
        temp_file,
        expected_schema,
        schema_error='B3 temporary Parquet schema is incompatible',
    )
    try:
        metadata = source.metadata
        if metadata is None:
            raise ExtractionError(
                str(temp_file), 'B3 temporary Parquet metadata is missing'
            )
        _validate_temporary_row_count(
            temp_file, metadata.num_rows, expected_rows=expected_rows
        )
        return source
    except BaseException:
        source.close()
        raise
