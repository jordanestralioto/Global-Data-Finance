"""Resolve annual B3 sources with bounded, ordered process preflight."""

from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator
from concurrent.futures import Future, TimeoutError
from contextlib import closing
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

from ....core.archive_safety import ArchiveSafetyLimits
from ....core.utils import SimpleProgressBar
from .async_execution import (
    check_phase_cancellation,
    set_phase_cancellation,
)
from .catalog import (
    AnnualResult,
    CatalogSelection,
    iter_serial_sources,
    resolve_annual_source,
    resolve_catalog_sources,
)
from .errors import CotahistCatalogError
from .executors import create_b3_executor
from .extraction_service.resource_policy import ResourcePolicyB3
from .models import CotahistCatalogResolution
from .processing import ProcessingModeEnumB3
from .source_validation import CotahistDocumentValidator
from .zip_reader import ZipFileReaderB3

_MIN_PREFLIGHT_SOURCE_BYTES = 64 * 1024**2


@dataclass(frozen=True)
class AnnualFailure:
    """Carry typed diagnostic causes as values across a process boundary."""

    error: CotahistCatalogError
    causes: tuple[BaseException, ...]

    @classmethod
    def capture(cls, error: CotahistCatalogError) -> AnnualFailure:
        """Retain the canonical validator's explicit exception chain."""
        causes: list[BaseException] = []
        cause = error.__cause__
        while cause is not None:
            causes.append(cause)
            cause = cause.__cause__
        return cls(error, tuple(causes))

    def raise_error(self) -> NoReturn:
        """Restore typed causes before raising the original catalog error."""
        parent: BaseException = self.error
        for cause in self.causes:
            parent.__cause__ = cause
            parent = cause
        raise self.error


def _has_large_workload(
    selection: CatalogSelection, years: tuple[int, ...]
) -> bool:
    """Admit large inputs and defer stat errors to canonical validation."""
    try:
        source_bytes = sum(
            path.stat().st_size
            for year in years
            for path in selection.candidates[year]
        )
    except OSError:
        return False
    return source_bytes >= _MIN_PREFLIGHT_SOURCE_BYTES


def resolve_extraction_sources(
    directory: str | Path,
    *,
    expected_years: Iterable[int] | None = None,
    target_tpmerc_codes: set[str] | None = None,
    all_markets: bool = True,
    limits: ArchiveSafetyLimits | None = None,
    processing_mode: ProcessingModeEnumB3 = ProcessingModeEnumB3.FAST,
    executor_backend: str = 'thread',
) -> CotahistCatalogResolution:
    """Preserve serial defaults and opt into eligible fast process requests."""
    return resolve_catalog_sources(
        directory,
        expected_years=expected_years,
        target_tpmerc_codes=target_tpmerc_codes,
        all_markets=all_markets,
        limits=limits,
        resolve_annual_sources=partial(
            _iter_preflight_sources,
            processing_mode=processing_mode,
            executor_backend=executor_backend,
        ),
    )


def init_preflight_worker(cancel_event: Any) -> None:
    """Bind cooperative cancellation to this child process's phase context."""
    set_phase_cancellation(cancel_event)


def _resolve_preflight_year(
    candidates: list[Path],
    year: int,
    selection: CatalogSelection,
) -> AnnualResult | AnnualFailure:
    """Reuse the annual source owner and its complete safety checks."""
    check_phase_cancellation()
    validator = CotahistDocumentValidator(
        ZipFileReaderB3(limits=selection.limits)
    )
    try:
        return resolve_annual_source(
            candidates,
            year=year,
            directory=selection.directory,
            validator=validator,
            target_tpmerc_codes=selection.codes,
            all_markets=selection.all_markets,
            limits=selection.limits,
        )
    except CotahistCatalogError as error:
        return AnnualFailure.capture(error)


def await_preflight(
    future: Future[AnnualResult | AnnualFailure],
) -> AnnualResult:
    """Poll cancellation without hiding an operation's own timeout failure."""
    while True:
        check_phase_cancellation()
        try:
            result = future.result(timeout=0.1)
        except TimeoutError:
            if not future.done():
                continue
            result = future.result()
        if isinstance(result, AnnualFailure):
            result.raise_error()
        return result


def _iter_preflight_sources(
    selection: CatalogSelection,
    *,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
) -> Iterator[AnnualResult]:
    """Report validated annual files while keeping worker cleanup scoped."""
    source_count = sum(
        bool(selection.candidates.get(year)) for year in selection.years
    )
    with (
        SimpleProgressBar(
            total=source_count,
            desc='Validating B3 files',
            operation='validation',
        ) as progress_bar,
        closing(
            _iter_preflight_results(
                selection,
                processing_mode=processing_mode,
                executor_backend=executor_backend,
            )
        ) as results,
    ):
        for result in results:
            progress_bar.update()
            yield result


def _iter_preflight_results(
    selection: CatalogSelection,
    *,
    processing_mode: ProcessingModeEnumB3,
    executor_backend: str,
) -> Generator[AnnualResult, None, None]:
    """Admit bounded work and join all children before reporting any result."""
    if (
        executor_backend != 'process'
        or processing_mode is not ProcessingModeEnumB3.FAST
    ):
        yield from iter_serial_sources(selection)
        return
    years = tuple(
        year for year in selection.years if selection.candidates.get(year)
    )
    policy = ResourcePolicyB3(processing_mode)
    workers = policy.worker_limit(len(years))
    if workers < 2 or not _has_large_workload(selection, years):
        yield from iter_serial_sources(selection)
        return
    executor, stop, _ = create_b3_executor(
        len(years),
        workers,
        processing_mode=processing_mode,
        executor_backend=executor_backend,
        initializer=init_preflight_worker,
    )
    active: dict[int, Future[AnnualResult | AnnualFailure]] = {}
    next_index = 0
    try:
        for index, _year in enumerate(years):
            check_phase_cancellation()
            while next_index < len(years) and len(active) < workers:
                check_phase_cancellation()
                year = years[next_index]
                active[next_index] = executor.submit(
                    _resolve_preflight_year,
                    selection.candidates[year],
                    year,
                    selection,
                )
                next_index += 1
            yield await_preflight(active.pop(index))
    finally:
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
