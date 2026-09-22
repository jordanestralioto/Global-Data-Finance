"""Isolated top-level worker for B3 multiprocessing extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .....core.archive_safety import ArchiveSafetyLimits
from ..cotahist_parser import CotahistParserB3
from ..zip_reader import ZipFileReaderB3
from .retry import retry_unpublished_io
from .types import SourceExtractionResult
from .zip_processor import ProcessingCancelled, ZipProcessorB3

_worker_cancel_event: Any | None = None


def init_worker(cancel_event: Any | None) -> None:
    """Initialize process-local reference to parent cancellation event.

    Args:
        cancel_event: Multiprocessing event created in spawn context.
    """
    global _worker_cancel_event
    _worker_cancel_event = cancel_event


def process_source_worker(
    source_path: str,
    target_tpmerc_codes: set[str],
    temp_output_path: str,
    *,
    python_record_limit: int = 25_000,
    archive_safety_limits: ArchiveSafetyLimits | None = None,
) -> SourceExtractionResult:
    """Execute isolated extraction for one COTAHIST source in a child process.

    Args:
        source_path: Absolute or relative path to the input COTAHIST file.
        target_tpmerc_codes: Filter set of B3 market type codes.
        temp_output_path: Staging path for the private temporary Parquet file.
        python_record_limit: Maximum buffered records before flushing to Arrow.
        archive_safety_limits: Safety bounds for decompression.

    Returns:
        SourceExtractionResult containing classification and output metadata.

    Raises:
        ProcessingCancelled: If cancelled cooperatively by the parent process.
        ExtractionError: If extraction, parsing, or writing fails.
    """
    source = Path(source_path)
    temp_output = Path(temp_output_path)
    global _worker_cancel_event
    cancel_event = _worker_cancel_event

    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled(str(source), 'Cancelled before processing')

    zip_reader = ZipFileReaderB3(limits=archive_safety_limits)
    zip_processor = ZipProcessorB3(
        zip_reader=zip_reader,
        parser_factory=CotahistParserB3,
        python_record_limit=python_record_limit,
        cancel_event=cancel_event,
    )

    return retry_unpublished_io(
        lambda: zip_processor.process(source, target_tpmerc_codes, temp_output)
    )
