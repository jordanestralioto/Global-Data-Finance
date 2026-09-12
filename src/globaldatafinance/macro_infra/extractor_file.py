"""Provide generic ZIP and text extraction primitives."""

import asyncio
import gc
import io
import time
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO

import pyarrow as pa  # type: ignore
import pyarrow.parquet as pq  # type: ignore

from ..core import get_logger
from ..core.archive_safety import (
    ArchiveSafetyLimits,
    open_limited_zip_member,
    validate_zip_archive,
)
from ..macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    ExtractionError,
)
from .read_files import ReadFilesAdapter

logger = get_logger(__name__)


class ExtractorAdapter:
    """Generic file extraction utilities for ZIP archives.

    This class provides low-level, reusable extraction methods that can be
    used across different parts of the application. Domain-specific logic
    (like CSV to Parquet conversion) should be implemented in dedicated
    modules within their respective domains.
    """

    CHUNK_SIZE_TXT = 8192
    CHUNK_SIZE_PARQUET = 50000

    @staticmethod
    def list_files_in_zip(
        zip_path: str,
        extension: str,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> list[str]:
        """List files in ZIP archive with optional extension filter.

        Args:
            zip_path: Path to the ZIP file
            extension: File extension to filter (e.g., '.csv', '.txt')
            archive_limits: Optional ZIP resource limits for this operation.

        Returns:
            List of filenames in the ZIP

        Raises:
            FileNotFoundError: If ZIP file doesn't exist
            CorruptedZipError: If ZIP file is invalid or corrupted
        """
        path = Path(zip_path)
        if not path.exists():
            raise FileNotFoundError(f'ZIP file not found: {zip_path}')

        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                infos = validate_zip_archive(path, z, limits=archive_limits)
                return [
                    info.filename
                    for info in infos
                    if not info.is_dir()
                    and info.filename.lower().endswith(extension)
                ]
        except zipfile.BadZipFile as e:
            raise CorruptedZipError(zip_path, str(e)) from e

    @staticmethod
    def open_file_from_zip(
        zip_file: zipfile.ZipFile,
        filename: str,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> IO[bytes]:
        """Open a file handle from an already-opened ZIP archive.

        This is useful for streaming large files without loading them entirely
        into memory. The caller is responsible for closing the returned handle.

        Args:
            zip_file: Already opened ZipFile object
            filename: Name of the file inside the ZIP to open
            archive_limits: Optional ZIP resource limits for this operation.

        Returns:
            File handle that can be read in chunks

        Raises:
            ExtractionError: If file not found in ZIP
        """
        archive_path = zip_file.filename or 'unknown.zip'
        if zip_file.filename is not None:
            validate_zip_archive(archive_path, zip_file, limits=archive_limits)
        if filename not in zip_file.namelist():
            raise ExtractionError(
                archive_path, f"File '{filename}' not found in ZIP"
            )

        return open_limited_zip_member(
            zip_file,
            filename,
            archive_path=archive_path,
            limits=archive_limits,
        )

    async def extract_txt_from_zip_async(
        self,
        zip_path: str,
        member_name: str | None = None,
        *,
        archive_limits: ArchiveSafetyLimits | None = None,
    ) -> AsyncIterator[str]:
        """Read ZIP TXT lines asynchronously with true streaming.

        This method is designed for COTAHIST files from B3 and uses
        true streaming without loading entire file into memory.

        Args:
            zip_path: Path to the ZIP file
            member_name: Explicit TXT member selected by a source adapter.
            archive_limits: Optional ZIP resource limits for this operation.

        Yields:
            Lines from the TXT file (decoded as latin-1)

        Raises:
            FileNotFoundError: If ZIP file doesn't exist
            CorruptedZipError: If ZIP file is invalid or corrupted
            ExtractionError: If no TXT file found in ZIP
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                infos = validate_zip_archive(
                    zip_path, zip_file, limits=archive_limits
                )
                selected_member = member_name
                if selected_member is None:
                    txt_files = [
                        info.filename
                        for info in infos
                        if not info.is_dir()
                        and info.filename.lower().endswith('.txt')
                    ]
                    if not txt_files:
                        raise ExtractionError(
                            zip_path, 'No .TXT file found in ZIP'
                        )
                    selected_member = txt_files[0]

                with ExtractorAdapter.open_file_from_zip(
                    zip_file,
                    selected_member,
                    archive_limits=archive_limits,
                ) as txt_file_handle:
                    for line_count, raw_line in enumerate(
                        txt_file_handle, start=1
                    ):
                        line = raw_line.decode(
                            'latin-1', errors='replace'
                        ).rstrip('\r\n')
                        yield line
                        if line_count % self.CHUNK_SIZE_TXT == 0:
                            await asyncio.sleep(0)
        except zipfile.BadZipFile as e:
            raise CorruptedZipError(zip_path, str(e)) from e
        except Exception as e:
            if isinstance(
                e, (ExtractionError, CorruptedZipError, FileNotFoundError)
            ):
                raise
            raise ExtractionError(
                zip_path, f'Error reading TXT from ZIP: {e}'
            ) from e

    def extract_csv_from_zip_to_parquet(
        self,
        zip_file: zipfile.ZipFile,
        parquet_path: Path,
        parquet_filename: str,
        csv_filename: str,
    ) -> None:
        """Extract single CSV from ZIP and convert to Parquet.

        Uses streaming processing to avoid loading entire CSV into memory.

        Args:
            zip_file: Open ZipFile object
            parquet_path: Full path for Parquet file
            parquet_filename: Parquet filename
            csv_filename: Name of CSV file inside ZIP

        Raises:
            ExtractionError: If CSV can't be read or converted
            DiskFullError: If insufficient disk space
        """
        logger.debug(
            'Processing %s -> %s with chunk size %s',
            csv_filename,
            parquet_filename,
            self.CHUNK_SIZE_PARQUET,
        )

        try:
            # Detect encoding first
            encoding = ReadFilesAdapter.read_csv_test_encoding(
                zip_file, csv_filename
            )

            self.__stream_csv_to_parquet(
                zip_file, csv_filename, parquet_path, encoding
            )

        except (DiskFullError, CorruptedZipError):
            self.__safe_delete_file(parquet_path)
            raise

        except Exception as e:
            self.__safe_delete_file(parquet_path)
            raise ExtractionError(
                str(parquet_path),
                f'Error converting {csv_filename} to Parquet: {e}',
            ) from e

    def __stream_csv_to_parquet(
        self,
        zip_file: zipfile.ZipFile,
        csv_filename: str,
        parquet_path: Path,
        encoding: str,
    ) -> None:
        """Stream CSV to Parquet using chunked processing.

        Args:
            zip_file: Open ZipFile object
            csv_filename: CSV filename
            parquet_path: Output Parquet path
            encoding: CSV encoding

        Raises:
            DiskFullError: If disk space exhausted
            Exception: On any streaming failure
        """
        writer = None
        writer_closed = False
        total_rows = 0

        try:
            with self.open_file_from_zip(zip_file, csv_filename) as csv_file:
                text_wrapper = io.TextIOWrapper(
                    csv_file,
                    encoding=encoding,
                    newline='',
                )
                csv_reader = ReadFilesAdapter.read_csv_chunk_size(
                    text_wrapper, chunk_size=self.CHUNK_SIZE_PARQUET
                )
                try:
                    for chunk_df in csv_reader:
                        table = pa.Table.from_pandas(
                            chunk_df,
                            preserve_index=False,
                        )

                        if writer is None:
                            writer = pq.ParquetWriter(
                                parquet_path,
                                table.schema,
                                compression='zstd',
                                compression_level=3,
                            )
                            logger.debug(f'Created {parquet_path.name}')

                        if not chunk_df.empty:
                            try:
                                writer.write_table(table)
                                total_rows += len(chunk_df)
                            except OSError as e:
                                if 'No space left on device' in str(e):
                                    raise DiskFullError(
                                        str(parquet_path)
                                    ) from e
                                raise
                finally:
                    csv_reader.close()
                    text_wrapper.close()

                if writer is not None:
                    writer.close()
                    writer_closed = True
                    self.__release_arrow_memory()
                    logger.debug(
                        f'Completed {csv_filename}: {total_rows} rows written'
                    )

        except Exception:
            if writer is not None and not writer_closed:
                try:
                    writer.close()
                except Exception as close_err:
                    logger.error(
                        f'Failed to close writer: {close_err}', exc_info=True
                    )
            raise
        finally:
            gc.collect()

    @staticmethod
    def __release_arrow_memory() -> None:
        """Return unused Arrow allocations after a bounded CSV stream."""
        release_unused = getattr(
            pa.default_memory_pool(), 'release_unused', None
        )
        if release_unused is not None:
            release_unused()

    def __safe_delete_file(
        self, file_path: Path, max_attempts: int = 3
    ) -> None:
        """Safely delete file with retry logic.

        Args:
            file_path: Path to file to delete
            max_attempts: Maximum deletion attempts

        Raises:
            ExtractionError: If file cannot be deleted after all attempts
        """
        if not file_path.exists():
            return

        for attempt in range(max_attempts):
            try:
                file_path.unlink()
                logger.debug(
                    f'Deleted {file_path.name} (attempt {attempt + 1})'
                )
                return
            except Exception as e:
                if attempt >= max_attempts - 1:
                    raise ExtractionError(
                        str(file_path),
                        f'Cannot delete file after {max_attempts} attempts: '
                        f'{e}. '
                        f'Manual intervention required.',
                    ) from e
                time.sleep(0.1 * (attempt + 1))
                logger.debug(
                    f'Retrying deletion of {file_path.name} '
                    f'(attempt {attempt + 2}/{max_attempts})'
                )
