"""Process validated COTAHIST rows into private Parquet output."""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from ......core import get_logger
from ......macro_exceptions import ExtractionError
from ...cotahist_parser import CotahistParserB3, CsvRow
from ...integrity import sha256_file
from ...models import ValidatedCotahistSource
from ...parquet_writer.session import (
    RECORD_BATCH_LIMIT,
    B3ParquetWriterSession,
)
from ...parquet_writer.verification import canonical_columns
from ...row_digest import B3OrderedRowDigest
from ..types import SourceExtractionResult
from .replay import LineReader, preflight_source, validate_source_replay
from .writer import write_csv_rows

logger = get_logger(__name__)


class ProcessingCancelled(ExtractionError):
    """Internal cooperative cancellation requested by the parent process."""

    def __init__(
        self, source: str, message: str = 'Extraction cancelled by parent'
    ) -> None:
        """Initialize cancellation error with source context.

        Args:
            source: Path or name of the source being processed.
            message: Informative cancellation explanation.
        """
        super().__init__(source, message)


CANCELLATION_LINE_STRIDE: int = 1_000


class ZipProcessorB3:
    """Write at most one private Arrow artifact for one source file."""

    def __init__(
        self,
        zip_reader: LineReader,
        parser_factory: Callable[[], CotahistParserB3] = CotahistParserB3,
        *,
        python_record_limit: int = RECORD_BATCH_LIMIT,
        cancel_event: Any | None = None,
    ) -> None:
        """Store factories; each worker receives an isolated parser state."""
        if python_record_limit <= 0:
            raise ValueError('python_record_limit must be positive')
        self.zip_reader = zip_reader
        self.parser_factory = parser_factory
        self.python_record_limit = python_record_limit
        self.cancel_event = cancel_event

    def _check_cancellation(self, source: Path) -> None:
        """Raise ProcessingCancelled when cancellation event was signaled."""
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ProcessingCancelled(str(source))

    def process(
        self,
        source_path: str | Path,
        target_tpmerc_codes: set[str],
        temp_output: Path,
        *,
        source_descriptor: ValidatedCotahistSource | None = None,
        all_markets: bool = False,
        schema_metadata: dict[bytes, bytes] | None = None,
    ) -> SourceExtractionResult:
        """Parse one source, keeping only a bounded list of Python records."""
        source = Path(source_path)
        self._check_cancellation(source)
        descriptor = source_descriptor or preflight_source(
            self.zip_reader, source, target_tpmerc_codes, all_markets
        )
        if descriptor.path.resolve() != source.resolve():
            raise ExtractionError(
                str(source),
                'Validated B3 source descriptor has a different path',
            )
        parser = self.parser_factory()
        session: B3ParquetWriterSession | None = None

        try:
            session, member, schema_fingerprint_value, parsed_digest = (
                self._process_strict_rows(
                    parser,
                    source,
                    target_tpmerc_codes,
                    temp_output,
                    descriptor,
                    all_markets,
                    schema_metadata,
                )
            )
            if session is not None:
                session.close()
                written = session.rows_written
            else:
                written = 0

            if (
                parser.metrics.selected_records
                != parser.metrics.parsed_records
                or parser.metrics.parsed_records != written
            ):
                raise ExtractionError(
                    str(source),
                    'B3 parser/write row-count invariant was violated',
                )
            return SourceExtractionResult(
                source_path=source,
                zip_member=member,
                source=descriptor,
                temp_path=temp_output if session is not None else None,
                selected_records=parser.metrics.selected_records,
                parsed_records=parser.metrics.parsed_records,
                written_records=written,
                metrics=parser.metrics,
                schema_fingerprint=schema_fingerprint_value,
                expected_rows_sha256=descriptor.expected_rows_sha256,
                parsed_rows_sha256=parsed_digest,
            )
        except ProcessingCancelled:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()
            with contextlib.suppress(OSError):
                temp_output.unlink(missing_ok=True)
            logger.info('B3 source processing cancelled: %s', source)
            raise
        except Exception:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()
            with contextlib.suppress(OSError):
                temp_output.unlink(missing_ok=True)
            logger.exception('B3 source processing failed: %s', source)
            raise

    def _process_strict_rows(
        self,
        parser: CotahistParserB3,
        source: Path,
        target_tpmerc_codes: set[str],
        temp_output: Path,
        descriptor: ValidatedCotahistSource,
        all_markets: bool,
        schema_metadata: dict[bytes, bytes] | None,
    ) -> tuple[B3ParquetWriterSession | None, str, str, str]:
        """Buffer canonical CSV rows for the production strict parser."""
        rows: list[CsvRow] = []
        session: B3ParquetWriterSession | None = None
        member = descriptor.member
        fingerprint = ''
        lines_read = 0
        content_digest = hashlib.sha256()
        rows_digest = B3OrderedRowDigest()

        def observe_batch(batch: Any) -> None:
            rows_digest.update_columns(canonical_columns(batch))

        cancellation_check = partial(self._check_cancellation, source)
        outer_digest = sha256_file(
            source, cancellation_check=cancellation_check
        )
        if outer_digest != descriptor.outer_sha256:
            raise ExtractionError(
                source.name,
                'COTAHIST input changed after catalog preflight',
            )
        try:
            self._check_cancellation(source)
            for raw_line in self.zip_reader.iter_raw_lines(
                str(source), expected_member=descriptor.member
            ):
                lines_read += 1
                if lines_read % CANCELLATION_LINE_STRIDE == 0:
                    self._check_cancellation(source)
                content_digest.update(raw_line.complete_bytes)
                context = raw_line.context
                member = context.zip_member or member
                row = parser._parse_bytes_to_csv_row(
                    raw_line.content,
                    target_tpmerc_codes,
                    context=context,
                    all_markets=all_markets,
                    source_year=descriptor.year,
                    source_sha256=descriptor.content_sha256,
                )
                if row is None:
                    continue
                rows.append(row)
                if len(rows) >= self.python_record_limit:
                    self._check_cancellation(source)
                    session, fingerprint = write_csv_rows(
                        session,
                        rows,
                        temp_output,
                        schema_metadata,
                        batch_observer=observe_batch,
                    )
            self._check_cancellation(source)
            if rows:
                session, fingerprint = write_csv_rows(
                    session,
                    rows,
                    temp_output,
                    schema_metadata,
                    batch_observer=observe_batch,
                )
            validate_source_replay(
                source,
                descriptor,
                parser,
                content_digest.hexdigest(),
                rows_digest.hexdigest(),
                cancellation_check=cancellation_check,
            )
            return session, member, fingerprint, rows_digest.hexdigest()
        except Exception:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()
            raise
        finally:
            rows.clear()
