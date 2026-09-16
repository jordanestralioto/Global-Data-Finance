from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    CotahistCatalogError,
    select_cotahist_file,
    validate_cotahist_catalog,
)
from globaldatafinance.core import ResourceState


class FakeResourceMonitor:
    def __init__(
        self,
        *,
        safe_worker_cap: int = 8,
        safe_batch_size: int | None = None,
        states: list[ResourceState] | None = None,
        process_memory_mb: float = 100.0,
    ) -> None:
        self.safe_worker_cap = safe_worker_cap
        self.safe_batch_size = safe_batch_size
        self.states = list(states or [ResourceState.HEALTHY])
        self.process_memory_mb = process_memory_mb
        self.worker_calls: list[int | None] = []
        self.batch_calls: list[int] = []
        self.check_calls = 0
        self._state_index = 0

    def get_safe_worker_count(self, desired: int | None) -> int:
        self.worker_calls.append(desired)
        if desired is None:
            return self.safe_worker_cap
        return min(desired, self.safe_worker_cap)

    def check_resources(self) -> ResourceState:
        if self._state_index < len(self.states):
            state = self.states[self._state_index]
            self._state_index += 1
        else:
            state = self.states[-1]
        self.check_calls += 1
        return state

    def get_safe_batch_size(self, desired_batch_size: int) -> int:
        self.batch_calls.append(desired_batch_size)
        if self.safe_batch_size is None:
            return desired_batch_size
        return self.safe_batch_size

    def get_process_memory_mb(self) -> float:
        return self.process_memory_mb


class DummyLoop:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple] = []

    async def run_in_executor(self, executor, func, *args):
        self.calls.append((executor, func, args))
        if self.result is None:
            return func(*args)
        return self.result


class FakeZipReader:
    def __init__(self, files: dict[str, list[str]] | None = None) -> None:
        self.files = files or {}
        self.calls: list[str] = []

    async def read_lines_from_zip(self, zip_path: str):
        self.calls.append(zip_path)
        for line in self.files.get(zip_path, []):
            yield line


class FakeParser:
    def __init__(self, responses: dict[str, dict] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, frozenset[str]]] = []

    def parse_line(self, line: str, target_codes: set[str]):
        self.calls.append((line, frozenset(target_codes)))
        if line in self.responses:
            return self.responses[line]
        if 'keep' in line:
            return {'value': line}
        return None


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def write_to_parquet(self, data, output_path: Path, mode: str):
        self.calls.append(
            {
                'records': list(data),
                'output_path': output_path,
                'mode': mode,
            }
        )


class DummyPool:
    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers
        self.shutdown_called = False

    def shutdown(
        self, wait: bool = False, cancel_futures: bool = False
    ) -> None:
        _ = wait, cancel_futures
        self.shutdown_called = True


def build_cotahist_line(tpmerc: str) -> str:
    line = [' '] * 245
    line[0:2] = list('01')
    line[2:10] = list('20240101')
    line[10:12] = list('02')
    ticker = 'TESTE12345678'[:12]
    line[12:24] = list(ticker)
    line[24:27] = list(tpmerc)
    return ''.join(line)


async def resources_available(timeout_seconds: int = 30) -> bool:
    """Return a deterministic successful resource wait for service tests."""
    _ = timeout_seconds
    return True


@pytest.fixture(autouse=True)
def suppress_execution_time_logging(monkeypatch):
    @contextmanager
    def noop(*_args, **_kwargs) -> Iterator[None]:
        yield

    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.extraction_service.service.log_execution_time',
        noop,
        raising=False,
    )


@pytest.fixture
def process_pool_spy(monkeypatch):
    created: list[DummyPool] = []

    def factory(max_workers: int | None = None):
        pool = DummyPool(max_workers)
        created.append(pool)
        return pool

    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.extraction_service.zip_processor.ThreadPoolExecutor',
        factory,
    )
    return created


_LOCAL_DATA_COMMAND = (
    'COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2023 '
    'uv run --locked --no-sync pytest -m "real_data and not slow"'
)


def _fail(message: str) -> NoReturn:
    pytest.fail(message, pytrace=False)


def _configured_dataset_path() -> Path:
    """Return the configured dataset directory or skip the opt-in suite."""
    configured_path = os.environ.get('COTAHIST_PATH')
    if not configured_path:
        pytest.skip(
            'COTAHIST_PATH is not set. Run the opt-in suite with: '
            f'{_LOCAL_DATA_COMMAND}'
        )
    return Path(configured_path).expanduser().resolve()


def _selected_year(files_by_year: dict[int, list[Path]]) -> int:
    """Resolve an exact configured year or infer the sole available year."""
    configured_year = os.environ.get('COTAHIST_TEST_YEAR')
    if configured_year is not None:
        if not re.fullmatch(r'\d{4}', configured_year):
            _fail('COTAHIST_TEST_YEAR must be exactly four digits')
        return int(configured_year)
    if len(files_by_year) == 1:
        return next(iter(files_by_year))
    available_years = ', '.join(str(year) for year in sorted(files_by_year))
    _fail(
        'COTAHIST_TEST_YEAR is required when COTAHIST_PATH contains multiple '
        f'years. Available years: {available_years}'
    )


def _select_file(files_by_year: dict[int, list[Path]], year: int) -> Path:
    """Select a deterministic ZIP-first input for the requested year."""
    return select_cotahist_file(files_by_year, year)


@pytest.fixture(scope='session')
def local_cotahist_catalog() -> dict[int, list[Path]]:
    """Index valid caller-owned COTAHIST inputs without processing rows."""
    dataset_path = _configured_dataset_path()
    try:
        return validate_cotahist_catalog(dataset_path)
    except CotahistCatalogError as error:
        _fail(str(error))


@pytest.fixture(scope='session')
def local_cotahist(
    local_cotahist_catalog: dict[int, list[Path]],
) -> tuple[Path, int]:
    """Resolve exactly one local year for an opt-in extraction test."""
    files_by_year = local_cotahist_catalog
    year = _selected_year(files_by_year)
    if year not in files_by_year:
        available_years = ', '.join(
            str(available_year) for available_year in sorted(files_by_year)
        )
        _fail(
            f'No valid COTAHIST input found for selected year '
            f'{year}. Available years: {available_years}'
        )
    return _select_file(files_by_year, year), year
