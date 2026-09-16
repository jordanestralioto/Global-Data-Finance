"""Atomic public B3 Parquet writing built on persistent Arrow sessions."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

from .....macro_exceptions import DiskFullError, ParquetWriteError
from .disk import check_disk_space
from .schema import build_b3_schema
from .session import (
    RECORD_BATCH_LIMIT,
    ROW_GROUP_LIMIT,
    B3ParquetWriterSession,
)


class ParquetWriterB3:
    """Write B3 records with overwrite and append compatibility semantics."""

    MIN_FREE_SPACE_MB = 100

    @staticmethod
    def _check_disk_space(path: Path, estimated_size_mb: float = 0) -> None:
        """Check the caller destination before creating a temporary output."""
        check_disk_space(
            path=path,
            estimated_size_mb=estimated_size_mb,
            min_free_space_mb=ParquetWriterB3.MIN_FREE_SPACE_MB,
        )

    async def write_to_parquet(
        self,
        data: list[dict[str, Any]],
        output_path: Path,
        mode: str = 'overwrite',
    ) -> None:
        """Write or append data through a validated same-filesystem temp."""
        if mode not in {'overwrite', 'append'}:
            raise ValueError(f'Unsupported Parquet write mode: {mode!r}')
        output_path = Path(output_path)
        self._check_disk_space(
            output_path, estimated_size_mb=max(len(data) * 0.001, 0.01)
        )
        temporary: Path | None = None
        try:
            temporary = self._create_temporary_path(output_path)
            schema = build_b3_schema()
            session = B3ParquetWriterSession().open(temporary, schema)
            if mode == 'append' and output_path.exists():
                self._copy_existing(output_path, session, schema)
            self._write_public_records(session, data)
            session.close()
            temporary.replace(output_path)
        except OSError as error:
            if getattr(error, 'errno', None) == 28 or 'No space left' in str(
                error
            ):
                raise DiskFullError(str(output_path)) from error
            raise ParquetWriteError(str(output_path), str(error)) from error
        finally:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_public_records(
        session: B3ParquetWriterSession, data: list[dict[str, Any]]
    ) -> None:
        """Preserve the caller's list while copying only bounded slices."""
        for offset in range(0, len(data), RECORD_BATCH_LIMIT):
            session.write_records(data[offset : offset + RECORD_BATCH_LIMIT])

    @staticmethod
    def _create_temporary_path(output_path: Path) -> Path:
        """Reserve a unique same-directory path for one public write.

        A fixed ``*.parquet.tmp`` name lets concurrent callers truncate or
        remove one another's in-flight artifacts.  ``mkstemp`` gives each
        operation an exclusive path on the destination filesystem while the
        final ``replace`` below remains the only publication operation.
        """
        descriptor, name = tempfile.mkstemp(
            prefix=f'.{output_path.name}.',
            suffix='.parquet.tmp',
            dir=output_path.parent,
        )
        try:
            os.close(descriptor)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(name).unlink(missing_ok=True)
            raise
        return Path(name)

    @staticmethod
    def _copy_existing(
        output_path: Path,
        session: B3ParquetWriterSession,
        expected_schema: object,
    ) -> None:
        """Copy old batches once after validating the canonical B3 schema."""
        import pyarrow.parquet as pq

        existing = pq.ParquetFile(output_path)
        if existing.schema_arrow != expected_schema:
            raise ParquetWriteError(
                str(output_path), 'Existing Parquet schema is incompatible'
            )
        session.write_batches(
            existing.iter_batches(batch_size=ROW_GROUP_LIMIT)
        )
