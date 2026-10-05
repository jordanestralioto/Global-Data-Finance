"""Define source reading and replay validation for extraction workers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from ......core.archive_safety import ArchiveSafetyLimits
from ......macro_exceptions import CorruptedZipError, ExtractionError
from ...catalog import resolve_cotahist_sources
from ...cotahist_parser import CotahistParserB3
from ...errors import CotahistCatalogError
from ...integrity import B3RawLine, sha256_file
from ...models import ValidatedCotahistSource

_SOURCE_YEAR_PATTERN = re.compile(
    r'^COTAHIST_A(?P<year>\d{4})\.(ZIP|TXT)$', re.IGNORECASE
)


class LineReader(Protocol):
    """Source reader contract required by one synchronous worker."""

    @property
    def limits(self) -> ArchiveSafetyLimits:
        """Return the archive safety limits used by this reader."""

    def iter_raw_lines(
        self,
        source_path: str,
        *,
        expected_member: str | None = None,
    ) -> Iterator[B3RawLine]:
        """Yield raw source lines with record context."""


def validate_source_replay(
    source: Path,
    descriptor: ValidatedCotahistSource,
    parser: CotahistParserB3,
    observed_content_sha256: str,
    observed_rows_sha256: str,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> None:
    """Reject source drift or any disagreement with immutable preflight."""
    if observed_content_sha256 != descriptor.content_sha256:
        raise ExtractionError(
            source.name,
            'COTAHIST uncompressed content changed after catalog preflight',
        )
    if (
        sha256_file(source, cancellation_check=cancellation_check)
        != descriptor.outer_sha256
    ):
        raise ExtractionError(
            source.name,
            'COTAHIST outer input changed after catalog preflight',
        )
    metrics = parser.metrics
    if (
        metrics.raw_quotes != descriptor.raw_quotes
        or metrics.selected_records != descriptor.selected_quotes
        or metrics.filtered_records != descriptor.intentional_exclusions
        or tuple(sorted(metrics.market_counts.items()))
        != descriptor.market_counts
    ):
        raise ExtractionError(
            source.name,
            'COTAHIST quotation counts changed after catalog preflight',
        )
    if observed_rows_sha256 != descriptor.expected_rows_sha256:
        raise ExtractionError(
            source.name,
            'COTAHIST canonical selected-row digest changed after '
            'catalog preflight',
        )


def preflight_source(
    zip_reader: LineReader,
    source: Path,
    target_tpmerc_codes: set[str],
    all_markets: bool,
) -> ValidatedCotahistSource:
    """Retain direct worker use by resolving one source through catalog."""
    match = _SOURCE_YEAR_PATTERN.fullmatch(source.name)
    if match is None:
        raise ExtractionError(
            str(source), 'B3 worker requires a COTAHIST annual filename'
        )
    year = int(match.group('year'))
    try:
        result = resolve_cotahist_sources(
            source.parent,
            expected_years={year},
            target_tpmerc_codes=target_tpmerc_codes,
            all_markets=all_markets,
            limits=zip_reader.limits,
        )
    except CotahistCatalogError as error:
        cause: BaseException | None = error
        while cause is not None:
            if isinstance(cause, CorruptedZipError):
                raise cause from error
            cause = cause.__cause__
        raise ExtractionError(str(source), str(error)) from error
    descriptor = next(
        (item for item in result.sources if item.path == source.resolve()),
        None,
    )
    if descriptor is None:
        raise ExtractionError(
            str(source),
            'B3 worker source is missing from the validated catalog',
        )
    return descriptor
