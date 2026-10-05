"""Resolve and fully preflight caller-owned annual COTAHIST sources."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from ....core.archive_safety import ArchiveSafetyLimits
from ....macro_exceptions import CorruptedZipError, ExtractionError
from .errors import CotahistCatalogError
from .input_validation import (
    COTAHIST_FILENAME_PATTERN,
    validate_cotahist_input,
)
from .models import CotahistCatalogResolution, ValidatedCotahistSource

if TYPE_CHECKING:
    from .source_validation import CotahistDocumentValidator


def resolve_cotahist_sources(
    directory: str | Path,
    *,
    expected_years: Iterable[int] | None = None,
    target_tpmerc_codes: set[str] | None = None,
    all_markets: bool = True,
    limits: ArchiveSafetyLimits | None = None,
) -> CotahistCatalogResolution:
    """Discover, reconcile, and validate every requested annual source.

    ZIP and TXT coexistence is accepted only when both complete uncompressed
    streams have identical SHA-256 identities. Missing requested years are
    returned explicitly so public extraction can report incomplete coverage.
    """
    catalog_path = _validate_directory(directory, allow_empty=True)
    from .source_validation import CotahistDocumentValidator
    from .zip_reader import ZipFileReaderB3

    candidates_by_year, years, missing = _select_candidate_years(
        catalog_path, expected_years
    )
    reader = ZipFileReaderB3(limits=limits)
    validator = CotahistDocumentValidator(reader)
    sources: list[ValidatedCotahistSource] = []
    ignored_duplicates: list[str] = []

    for year in years:
        candidates = candidates_by_year.get(year, [])
        if not candidates:
            continue
        try:
            source, duplicate = _resolve_annual_source(
                candidates,
                year=year,
                directory=catalog_path,
                validator=validator,
                target_tpmerc_codes=target_tpmerc_codes or set(),
                all_markets=all_markets,
                limits=limits,
            )
        except CotahistCatalogError as error:
            error.resolution = CotahistCatalogResolution(
                sources=tuple(sources),
                missing_years=missing,
                ignored_duplicate_sources=tuple(ignored_duplicates),
            )
            error.resolved_file_count = sum(
                bool(candidates_by_year.get(requested_year))
                for requested_year in years
            )
            raise
        sources.append(source)
        if duplicate is not None:
            ignored_duplicates.append(duplicate)

    return CotahistCatalogResolution(
        sources=tuple(
            sorted(
                sources,
                key=lambda source: (
                    source.year,
                    *_candidate_sort_key(source.path),
                ),
            )
        ),
        missing_years=missing,
        ignored_duplicate_sources=tuple(sorted(ignored_duplicates)),
    )


def _resolve_annual_source(
    candidates: list[Path],
    *,
    year: int,
    directory: Path,
    validator: CotahistDocumentValidator,
    target_tpmerc_codes: set[str],
    all_markets: bool,
    limits: ArchiveSafetyLimits | None,
) -> tuple[ValidatedCotahistSource, str | None]:
    """Validate all annual representations before selecting one source."""
    _reject_same_format_conflicts(candidates, year, directory)
    validated: list[ValidatedCotahistSource] = []
    for candidate in sorted(candidates, key=_candidate_sort_key):
        try:
            member = validate_cotahist_input(candidate, limits=limits)
            validated.append(
                validator.validate(
                    candidate,
                    year=year,
                    member=member or '',
                    target_tpmerc_codes=target_tpmerc_codes,
                    all_markets=all_markets,
                )
            )
        except (
            CotahistCatalogError,
            CorruptedZipError,
            ExtractionError,
            OSError,
        ) as error:
            raise CotahistCatalogError(
                f'Invalid COTAHIST source {candidate.name}: '
                f'{type(error).__name__}: {error}',
                source_path=candidate,
            ) from error
    selected = validated[0]
    if len(validated) == 1:
        return selected, None
    duplicate = validated[1]
    if selected.content_sha256 != duplicate.content_sha256:
        raise CotahistCatalogError(
            f'Conflicting ZIP and TXT COTAHIST contents for year '
            f'{year}: {selected.path.name}, {duplicate.path.name}',
            source_path=duplicate.path,
        )
    return selected, str(duplicate.path)


def index_cotahist_catalog(
    directory: str | Path,
    *,
    expected_years: Iterable[int] | None = None,
    limits: ArchiveSafetyLimits | None = None,
) -> dict[int, list[Path]]:
    """Select container-validated inputs for an evidence manifest.

    Quotation validation remains owned by extraction. Coexisting ZIP/TXT
    inputs use the full resolver to retain its content-equivalence rule.
    """
    catalog_path = _validate_directory(directory, allow_empty=True)
    candidates_by_year, years, missing = _select_candidate_years(
        catalog_path, expected_years
    )
    if missing:
        raise CotahistCatalogError(
            f'COTAHIST catalog is missing years: {list(missing)}'
        )
    catalog: dict[int, list[Path]] = {}
    for year in years:
        candidates = candidates_by_year[year]
        if len(candidates) == 1:
            validate_cotahist_input(candidates[0], limits=limits)
            catalog[year] = [candidates[0]]
        else:
            resolved = resolve_cotahist_sources(
                catalog_path, expected_years=(year,), limits=limits
            )
            catalog[year] = [resolved.sources[0].path]
    return catalog


def validate_cotahist_catalog(
    directory: str | Path,
    *,
    expected_years: Iterable[int] | None = None,
    limits: ArchiveSafetyLimits | None = None,
) -> dict[int, list[Path]]:
    """Validate a catalog using the same full preflight as extraction.

    Unrelated years are ignored when ``expected_years`` is supplied. Every
    discovered year is validated when no range is supplied.
    """
    result = resolve_cotahist_sources(
        directory,
        expected_years=expected_years,
        all_markets=True,
        limits=limits,
    )
    if result.missing_years:
        raise CotahistCatalogError(
            f'COTAHIST catalog is missing years: {list(result.missing_years)}'
        )
    return {source.year: [source.path] for source in result.sources}


def select_cotahist_file(
    files_by_year: dict[int, list[Path]], year: int
) -> Path:
    """Select the ZIP-first input for one already-validated year."""
    try:
        candidates = files_by_year[year]
    except KeyError as error:
        available = ', '.join(str(item) for item in sorted(files_by_year))
        raise CotahistCatalogError(
            f'No COTAHIST input found for year {year}; available: {available}'
        ) from error
    return sorted(candidates, key=_candidate_sort_key)[0]


def _validate_directory(directory: str | Path, *, allow_empty: bool) -> Path:
    catalog_path = Path(directory).expanduser().resolve()
    if not catalog_path.exists():
        raise CotahistCatalogError(
            f'COTAHIST directory does not exist: {catalog_path}'
        )
    if not catalog_path.is_dir():
        raise CotahistCatalogError(
            f'COTAHIST path is not a directory: {catalog_path}'
        )
    try:
        children = list(catalog_path.iterdir())
    except OSError as error:
        raise CotahistCatalogError(
            f'COTAHIST directory cannot be inspected: {catalog_path}'
        ) from error
    if not children and not allow_empty:
        raise CotahistCatalogError(
            f'COTAHIST directory is empty: {catalog_path}'
        )
    return catalog_path


def _discover_candidates(directory: Path) -> dict[int, list[Path]]:
    """Index names only; content checks happen after year selection."""
    candidates_by_year: dict[int, list[Path]] = {}
    for candidate in sorted(directory.iterdir(), key=lambda path: path.name):
        if not candidate.is_file():
            continue
        match = COTAHIST_FILENAME_PATTERN.fullmatch(candidate.name)
        if match is None:
            continue
        year = int(match.group('year'))
        candidates_by_year.setdefault(year, []).append(candidate)
    return candidates_by_year


def _select_candidate_years(
    directory: Path, expected_years: Iterable[int] | None
) -> tuple[dict[int, list[Path]], tuple[int, ...], tuple[int, ...]]:
    """Share deterministic source discovery and requested-year coverage."""
    candidates = _discover_candidates(directory)
    years = (
        tuple(sorted(candidates))
        if expected_years is None
        else tuple(sorted(set(expected_years)))
    )
    missing = tuple(year for year in years if year not in candidates)
    return candidates, years, missing


def _reject_same_format_conflicts(
    candidates: list[Path], year: int, directory: Path
) -> None:
    """Reject ambiguous same-format annual inputs before opening content."""
    extensions = [path.suffix.casefold() for path in candidates]
    if extensions.count('.zip') > 1 or extensions.count('.txt') > 1:
        names = ', '.join(path.name for path in candidates)
        raise CotahistCatalogError(
            f'Conflicting COTAHIST inputs for year {year} in '
            f'{directory}: {names}'
        )


def _candidate_sort_key(path: Path) -> tuple[bool, str, str]:
    """Prefer ZIP then use a deterministic case-insensitive basename order."""
    return path.suffix.casefold() != '.zip', path.name.casefold(), path.name
