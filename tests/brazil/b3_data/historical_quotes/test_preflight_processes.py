"""Compare concurrent preflight with the canonical serial owner."""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from globaldatafinance.brazil.b3_data.historical_quotes.preflight import (
    resolve_extraction_sources,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def small_lifecycle_workload_policy(monkeypatch):
    """Exercise real worker lifecycle with a small deterministic corpus."""
    import os

    from globaldatafinance.brazil.b3_data.historical_quotes import preflight

    monkeypatch.setattr(preflight, '_MIN_PREFLIGHT_SOURCE_BYTES', 1)
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', '2')
    monkeypatch.setattr(os, 'cpu_count', lambda: 4)
    monkeypatch.setattr(
        preflight.ResourcePolicyB3,
        '_read_available_memory_mib',
        staticmethod(lambda: 2048),
    )


def parallel_preflight(directory, **kwargs):
    return resolve_extraction_sources(
        directory, executor_backend='process', **kwargs
    )


def _sources(root):
    for year in (2023, 2024, 2025):
        write_cotahist_txt(
            root, year=year, records=[build_cotahist_record(year=year)]
        )


def test_concurrent_catalog_preserves_order_and_exact_descriptors(
    tmp_path,
):
    _sources(tmp_path)
    expected = resolve_cotahist_sources(
        tmp_path, expected_years=(2022, 2023, 2024, 2025, 2026)
    )
    observed = parallel_preflight(
        tmp_path, expected_years=(2022, 2023, 2024, 2025, 2026)
    )
    assert observed == expected
    assert observed.missing_years == (2022, 2026)
    assert [source.year for source in observed.sources] == [2023, 2024, 2025]


def test_concurrent_catalog_preserves_zip_txt_duplicate_selection(tmp_path):
    _sources(tmp_path)
    write_cotahist_zip(
        tmp_path, year=2023, records=[build_cotahist_record(year=2023)]
    )
    expected = resolve_cotahist_sources(tmp_path)
    observed = parallel_preflight(tmp_path)
    assert observed == expected
    assert observed.sources[0].path.suffix.lower() == '.zip'
    assert len(observed.ignored_duplicate_sources) == 1


@pytest.mark.parametrize(
    'corruption', ['record_length', 'invalid_date', 'conflicting_formats']
)
def test_concurrent_catalog_preserves_failed_year_and_completed_prefix(
    tmp_path, corruption
):
    _sources(tmp_path)
    if corruption == 'record_length':
        (tmp_path / 'COTAHIST_A2024.TXT').write_bytes(
            b'not a COTAHIST document\n'
        )
    elif corruption == 'invalid_date':
        quote = build_cotahist_record(year=2024)
        write_cotahist_txt(
            tmp_path, year=2024, records=[quote[:2] + '20241315' + quote[10:]]
        )
    else:
        write_cotahist_zip(
            tmp_path,
            year=2024,
            records=[build_cotahist_record(year=2024, ticker='VALE3')],
        )
    with pytest.raises(CotahistCatalogError) as serial:
        resolve_cotahist_sources(tmp_path)
    with pytest.raises(CotahistCatalogError) as concurrent:
        parallel_preflight(tmp_path)
    assert str(concurrent.value) == str(serial.value)
    assert concurrent.value.source_path == serial.value.source_path
    assert concurrent.value.resolution == serial.value.resolution
    assert (
        concurrent.value.resolved_file_count
        == serial.value.resolved_file_count
    )
    for observed, expected in zip(
        _cause_chain(concurrent.value), _cause_chain(serial.value), strict=True
    ):
        assert type(observed) is type(expected)
        assert str(observed) == str(expected)


def _cause_chain(error):
    chain = []
    while error is not None:
        chain.append(error)
        error = error.__cause__
    return chain


@pytest.mark.asyncio
async def test_repeated_cancellation_joins_spawned_preflight_workers(
    tmp_path, monkeypatch
):
    import asyncio
    import multiprocessing
    import os
    from contextlib import suppress

    from globaldatafinance.brazil.b3_data.historical_quotes import (
        async_execution,
    )
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        preflight as probe,
    )
    from tests.support.preflight_workers import cancellable_annual

    _sources(tmp_path)
    monkeypatch.setattr(probe, '_resolve_preflight_year', cancellable_annual)
    before = {child.pid for child in multiprocessing.active_children()}
    task = asyncio.create_task(
        async_execution.run_blocking_phase(
            probe.resolve_extraction_sources,
            tmp_path,
            executor_backend='process',
        )
    )
    try:
        async with asyncio.timeout(15):
            while not list(tmp_path.glob('*.started')):
                await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=10)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    started = list(tmp_path.glob('*.started'))
    assert started
    assert all(int(marker.read_text()) != os.getpid() for marker in started)
    assert all(marker.with_suffix('.stopped').exists() for marker in started)
    assert {child.pid for child in multiprocessing.active_children()} == before
    assert not list(tmp_path.glob('*.parquet'))


def test_one_worker_preflight_uses_canonical_serial_resolver(
    tmp_path, monkeypatch
):
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        preflight as probe,
    )

    _sources(tmp_path)
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', '1')
    monkeypatch.setattr(
        probe,
        'create_b3_executor',
        lambda *_args, **_kwargs: pytest.fail(
            'One-worker preflight must not create an executor'
        ),
    )
    expected = resolve_cotahist_sources(tmp_path)
    observed = parallel_preflight(tmp_path)
    assert observed == expected


@pytest.mark.parametrize(
    'backend,mode', [('thread', 'fast'), ('process', 'slow')]
)
def test_serial_profiles_do_not_construct_a_process_executor(
    tmp_path, monkeypatch, backend, mode
):
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        preflight as probe,
    )
    from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
        ProcessingModeEnumB3,
    )

    _sources(tmp_path)
    monkeypatch.setattr(
        probe,
        'create_b3_executor',
        lambda *_args, **_kwargs: pytest.fail(
            'Serial profile must not create an executor'
        ),
    )
    expected = resolve_cotahist_sources(tmp_path)
    observed = resolve_extraction_sources(
        tmp_path,
        executor_backend=backend,
        processing_mode=ProcessingModeEnumB3(mode),
    )
    assert observed == expected


def test_public_facade_uses_opted_in_preflight_and_publishes_verified_rows(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    from globaldatafinance import HistoricalQuotesB3
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        preflight as probe,
    )
    from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
        ProcessingModeEnumB3,
    )

    sources = tmp_path / 'sources'
    sources.mkdir()
    _sources(sources)
    destination = tmp_path / 'output'
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'process')
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', '2')
    factory = Mock(wraps=probe.create_b3_executor)
    monkeypatch.setattr(probe, 'create_b3_executor', factory)
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(sources),
        assets_list=['todos'],
        initial_year=2023,
        last_year=2025,
        destination_path=str(destination),
        output_filename='quotes',
        processing_mode='fast',
        verbose=False,
    )
    factory.assert_called_once_with(
        3,
        2,
        processing_mode=ProcessingModeEnumB3.FAST,
        executor_backend='process',
        initializer=probe.init_preflight_worker,
    )
    assert result['success'] is True
    assert result['integrity']['status'] == 'passed'
    assert result['total_records'] == 3
    assert result['integrity']['verified_rows'] == 3
    assert result['integrity']['selected_years'] == [2023, 2024, 2025]
    assert (destination / 'quotes.parquet').is_file()


def test_small_workload_preserves_serial_preflight(tmp_path, monkeypatch):
    from globaldatafinance.brazil.b3_data.historical_quotes import preflight

    _sources(tmp_path)
    monkeypatch.setattr(preflight, '_MIN_PREFLIGHT_SOURCE_BYTES', 64 * 1024**2)
    monkeypatch.setattr(
        preflight,
        'create_b3_executor',
        lambda *_args, **_kwargs: pytest.fail(
            'Small preflight must stay serial'
        ),
    )

    observed = parallel_preflight(tmp_path)

    assert observed == resolve_cotahist_sources(tmp_path)


@pytest.mark.parametrize('threshold_offset', [-1, 0, 1])
def test_preflight_admission_uses_total_stored_candidate_bytes(
    tmp_path, monkeypatch, threshold_offset
):
    from unittest.mock import Mock

    from globaldatafinance.brazil.b3_data.historical_quotes import preflight

    _sources(tmp_path)
    write_cotahist_zip(
        tmp_path, year=2023, records=[build_cotahist_record(year=2023)]
    )
    total_bytes = sum(path.stat().st_size for path in tmp_path.iterdir())
    monkeypatch.setattr(
        preflight,
        '_MIN_PREFLIGHT_SOURCE_BYTES',
        total_bytes + threshold_offset,
    )
    factory = Mock(wraps=preflight.create_b3_executor)
    monkeypatch.setattr(preflight, 'create_b3_executor', factory)

    observed = parallel_preflight(tmp_path)

    assert observed == resolve_cotahist_sources(tmp_path)
    assert factory.call_count == int(threshold_offset <= 0)
