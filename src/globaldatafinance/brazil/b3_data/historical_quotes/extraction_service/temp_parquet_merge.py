"""Ordered streaming merge for transaction-private B3 Parquet artifacts."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .....macro_exceptions import ExtractionError, ParquetWriteError
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
            written_before = session.rows_written
            session.write_batches(
                source.iter_batches(batch_size=ROW_GROUP_LIMIT)
            )
            if session.rows_written < written_before:
                raise ExtractionError(
                    str(temp_file), 'B3 merge row count regressed unexpectedly'
                )
        session.close()
        return session.rows_written
    except Exception as error:
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


def validate_one_temp_file(
    temp_file: Path,
    expected_schema: Schema,
    expected_rows: int,
) -> int:
    """Validate one source artifact before publishing it without a merge.

    The one-source path is logically a degenerate ordered merge.  It keeps
    the same integrity checks as the multi-source implementation while
    avoiding a needless read-and-rewrite of a fully validated Parquet file.
    """
    _validate_merge_inputs([temp_file], [expected_rows])
    source = _open_validated_temporary(
        temp_file, expected_schema, expected_rows
    )
    metadata = source.metadata
    if metadata is None:
        raise ExtractionError(
            str(temp_file), 'B3 temporary Parquet metadata is missing'
        )
    return cast(int, metadata.num_rows)


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
    import pyarrow.parquet as pq

    if not temp_file.is_file():
        raise ExtractionError(
            str(temp_file), 'B3 temporary Parquet artifact is missing'
        )
    source = pq.ParquetFile(temp_file)
    if source.schema_arrow != expected_schema:
        raise ExtractionError(
            str(temp_file), 'B3 temporary Parquet schema is incompatible'
        )
    metadata = source.metadata
    if metadata is None:
        raise ExtractionError(
            str(temp_file), 'B3 temporary Parquet metadata is missing'
        )
    _validate_temporary_row_count(temp_file, metadata.num_rows, expected_rows)
    return source
