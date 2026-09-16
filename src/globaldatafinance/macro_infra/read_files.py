"""Read CSV members from ZIP archives using a deterministic encoding policy."""

from __future__ import annotations

import codecs
import csv
import zipfile
from typing import IO, Any

from ..core import get_logger
from ..core.archive_safety import open_limited_zip_member
from ..macro_exceptions import ExtractionError

logger = get_logger(__name__)


class ReadFilesAdapter:
    """Provide low-level CSV reading helpers for archive adapters."""

    _ENCODING_CHUNK_SIZE = 64 * 1024
    _UTF8_BOM = codecs.BOM_UTF8
    _SUPPORTED_ENCODINGS = ('utf-8', 'cp1252', 'latin-1')

    @staticmethod
    def read_csv_test_encoding(
        zip_file: zipfile.ZipFile, csv_filename: str
    ) -> str:
        """Detect correct encoding for CSV file.

        Args:
            zip_file: Open ZipFile object
            csv_filename: CSV filename

        Returns:
            Working encoding string

        Raises:
            ExtractionError: If no encoding works
        """
        if ReadFilesAdapter._has_utf8_bom(zip_file, csv_filename):
            try:
                ReadFilesAdapter._validate_full_member_encoding(
                    zip_file, csv_filename, 'utf-8-sig'
                )
            except (UnicodeDecodeError, LookupError) as error:
                raise ExtractionError(
                    csv_filename,
                    'UTF-8 BOM is present but the complete member is not '
                    'valid UTF-8',
                ) from error
            logger.debug('Validated %s with encoding utf-8-sig', csv_filename)
            return 'utf-8-sig'

        last_error: Exception | None = None
        for encoding in ReadFilesAdapter._SUPPORTED_ENCODINGS:
            try:
                ReadFilesAdapter._validate_full_member_encoding(
                    zip_file, csv_filename, encoding
                )
            except (UnicodeDecodeError, LookupError) as error:
                last_error = error
                continue
            logger.debug(
                'Validated %s with encoding %s', csv_filename, encoding
            )
            return encoding
        raise ExtractionError(
            csv_filename,
            f'Could not read {csv_filename} with any encoding '
            f'(tried {", ".join(ReadFilesAdapter._SUPPORTED_ENCODINGS)})',
        ) from last_error

    @staticmethod
    def _has_utf8_bom(zip_file: zipfile.ZipFile, csv_filename: str) -> bool:
        """Inspect a bounded stream without consuming later processing."""
        with open_limited_zip_member(zip_file, csv_filename) as csv_file:
            return csv_file.read(len(ReadFilesAdapter._UTF8_BOM)) == (
                ReadFilesAdapter._UTF8_BOM
            )

    @staticmethod
    def _validate_full_member_encoding(
        zip_file: zipfile.ZipFile,
        csv_filename: str,
        encoding: str,
    ) -> None:
        """Decode every byte of a member in constant-size streaming chunks."""
        decoder = codecs.getincrementaldecoder(encoding)(errors='strict')
        with open_limited_zip_member(zip_file, csv_filename) as csv_file:
            while chunk := csv_file.read(
                ReadFilesAdapter._ENCODING_CHUNK_SIZE
            ):
                decoder.decode(chunk, final=False)
        decoder.decode(b'', final=True)

    @staticmethod
    def read_csv_chunk_size(text_wrapper: IO[str], chunk_size: int) -> Any:
        """Read a CSV stream in pandas chunks using the project delimiter."""
        import pandas as pd

        return pd.read_csv(
            text_wrapper,
            sep=';',
            quoting=csv.QUOTE_NONE,
            on_bad_lines='error',
            chunksize=chunk_size,
        )
