"""Synchronous, bounded processing of one B3 COTAHIST input."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol, cast

from .....core import get_logger
from .....macro_exceptions import ExtractionError
from ..cotahist_parser import B3ParserMetrics, CotahistParserB3, CsvRow
from ..integrity import B3RecordContext
from ..parquet_writer.schema import build_b3_schema, schema_fingerprint
from ..parquet_writer.session import RECORD_BATCH_LIMIT, B3ParquetWriterSession
from .types import SourceExtractionResult

logger = get_logger(__name__)


class _LineReader(Protocol):
    """Source reader contract required by one synchronous worker."""

    def iter_lines(
        self, source_path: str
    ) -> Iterator[tuple[str, B3RecordContext]]: ...


class _LineParser(Protocol):
    """Strict source-local parser contract."""

    metrics: B3ParserMetrics

    def parse_line(
        self,
        line: str,
        target_codes: set[str],
        context: B3RecordContext | None = None,
    ) -> dict[str, object] | None: ...


class ZipProcessorB3:
    """Write at most one private Arrow artifact for one source file."""

    def __init__(
        self,
        zip_reader: _LineReader,
        parser_factory: Callable[[], _LineParser] = CotahistParserB3,
        *,
        python_record_limit: int = RECORD_BATCH_LIMIT,
    ) -> None:
        """Store factories; each worker receives an isolated parser state."""
        if python_record_limit <= 0:
            raise ValueError('python_record_limit must be positive')
        self.zip_reader = zip_reader
        self.parser_factory = parser_factory
        self.python_record_limit = python_record_limit

    def process(
        self,
        source_path: str | Path,
        target_tpmerc_codes: set[str],
        temp_output: Path,
    ) -> SourceExtractionResult:
        """Parse one source, keeping only a bounded list of Python records."""
        source = Path(source_path)
        parser = self.parser_factory()
        session: B3ParquetWriterSession | None = None

        try:
            if type(parser) is CotahistParserB3:
                session, member, schema_fingerprint_value = (
                    self._process_strict_rows(
                        cast(CotahistParserB3, parser),
                        source,
                        target_tpmerc_codes,
                        temp_output,
                    )
                )
            else:
                session, member, schema_fingerprint_value = (
                    self._process_generic_records(
                        parser,
                        source,
                        target_tpmerc_codes,
                        temp_output,
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
                temp_path=temp_output if session is not None else None,
                selected_records=parser.metrics.selected_records,
                parsed_records=parser.metrics.parsed_records,
                written_records=written,
                metrics=parser.metrics,
                schema_fingerprint=schema_fingerprint_value,
            )
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
    ) -> tuple[B3ParquetWriterSession | None, str, str]:
        """Buffer canonical CSV rows for the production strict parser."""
        rows: list[CsvRow] = []
        session: B3ParquetWriterSession | None = None
        member = source.name
        fingerprint = ''
        try:
            for line, context in self.zip_reader.iter_lines(str(source)):
                member = context.zip_member or member
                row = parser.parse_line_to_csv_row(
                    line, target_tpmerc_codes, context=context
                )
                if row is None:
                    continue
                rows.append(row)
                if len(rows) >= self.python_record_limit:
                    session, fingerprint = self._write_csv_rows(
                        session, rows, temp_output
                    )
            if rows:
                session, fingerprint = self._write_csv_rows(
                    session, rows, temp_output
                )
            return session, member, fingerprint
        except Exception:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()
            raise
        finally:
            rows.clear()

    def _process_generic_records(
        self,
        parser: _LineParser,
        source: Path,
        target_tpmerc_codes: set[str],
        temp_output: Path,
    ) -> tuple[B3ParquetWriterSession | None, str, str]:
        """Retain a bounded fallback for custom parser collaborators."""
        records: list[dict[str, object]] = []
        session: B3ParquetWriterSession | None = None
        member = source.name
        fingerprint = ''
        try:
            for line, context in self.zip_reader.iter_lines(str(source)):
                member = context.zip_member or member
                parsed = parser.parse_line(
                    line, target_tpmerc_codes, context=context
                )
                if parsed is None:
                    continue
                records.append(parsed)
                if len(records) >= self.python_record_limit:
                    session, fingerprint = self._write_records(
                        session, records, temp_output
                    )
            if records:
                session, fingerprint = self._write_records(
                    session, records, temp_output
                )
            return session, member, fingerprint
        except Exception:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()
            raise
        finally:
            records.clear()

    @staticmethod
    def _write_records(
        session: B3ParquetWriterSession | None,
        records: list[dict[str, object]],
        temp_output: Path,
    ) -> tuple[B3ParquetWriterSession, str]:
        """Open the lazy Arrow writer on first data and empty the buffer."""
        session, fingerprint = ZipProcessorB3._session_for_write(
            session, temp_output
        )
        session.write_records(records)
        return session, fingerprint

    @staticmethod
    def _write_csv_rows(
        session: B3ParquetWriterSession | None,
        rows: list[CsvRow],
        temp_output: Path,
    ) -> tuple[B3ParquetWriterSession, str]:
        """Write strict parser rows without a typed-dictionary round trip."""
        session, fingerprint = ZipProcessorB3._session_for_write(
            session, temp_output
        )
        session.write_csv_rows(rows)
        return session, fingerprint

    @staticmethod
    def _session_for_write(
        session: B3ParquetWriterSession | None,
        temp_output: Path,
    ) -> tuple[B3ParquetWriterSession, str]:
        """Create or validate the one lazy Arrow session for a source."""
        if session is None:
            schema = build_b3_schema()
            session = B3ParquetWriterSession().open(temp_output, schema)
            fingerprint = schema_fingerprint(schema)
        else:
            if session.schema is None:
                raise RuntimeError('B3 writer session lost its schema')
            fingerprint = schema_fingerprint(session.schema)
        return session, fingerprint
