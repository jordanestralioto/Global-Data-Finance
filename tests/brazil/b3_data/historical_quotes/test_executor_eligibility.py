"""Choose spawned processes only for eligible caller contexts and resources."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    executors,
    preflight,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt


@pytest.mark.unit
@pytest.mark.parametrize('setting', [None, 'thread', 'process'])
def test_public_backend_default_and_explicit_overrides(
    monkeypatch: pytest.MonkeyPatch, setting: str | None
) -> None:
    """Facade construction selects processes by default without spawning."""
    if setting is None:
        monkeypatch.delenv('GDF_B3_EXECUTOR_BACKEND', raising=False)
    else:
        monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', setting)
    assert HistoricalQuotesB3()._extract_use_case.executor_backend == (
        setting or 'process'
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'context', ['daemon', 'interactive', 'stdin', 'missing']
)
def test_known_incompatible_contexts_log_a_reason_before_submission(
    monkeypatch: pytest.MonkeyPatch, context: str
) -> None:
    """Known spawn restrictions select threads without running a child."""
    main = SimpleNamespace(__spec__=None)
    if context == 'stdin':
        main.__file__ = '<stdin>'
    elif context == 'missing':
        main.__file__ = '/nonexistent/gdf-main.py'
    monkeypatch.setitem(sys.modules, '__main__', main)
    monkeypatch.setattr(
        executors.mp,
        'current_process',
        lambda: SimpleNamespace(daemon=context == 'daemon'),
    )
    logged = Mock()
    monkeypatch.setattr(executors.logger, 'info', logged)
    executor, stop, processes = executors.create_b3_executor(
        2,
        2,
        processing_mode=ProcessingModeEnumB3.FAST,
        executor_backend='process',
        initializer=lambda _stop: None,
    )
    try:
        assert processes is False
        assert executor.submit(lambda: 42).result() == 42
        logged.assert_called_once()
        assert logged.call_args.args[1]
    finally:
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.unit
@pytest.mark.parametrize('entrypoint', ['module', 'script'])
def test_eligibility_uses_metadata_without_executing_caller_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entrypoint: str
) -> None:
    """An importable spec or readable script is sufficient caller evidence."""
    main = SimpleNamespace(__spec__=None)
    if entrypoint == 'module':
        main.__spec__ = SimpleNamespace(name='caller.main', loader=object())
    else:
        script = tmp_path / 'main.py'
        script.write_text('raise AssertionError("must not execute")\n')
        main.__file__ = str(script)
    monkeypatch.setitem(sys.modules, '__main__', main)
    assert executors._spawn_incompatibility_reason() is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ('count', 'workers', 'mode', 'backend'),
    [
        (1, 4, 'fast', 'process'),
        (2, 1, 'fast', 'process'),
        (2, 4, 'slow', 'process'),
        (2, 4, 'fast', 'thread'),
    ],
)
def test_ineligible_profiles_do_not_probe_spawn(
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    workers: int,
    mode: str,
    backend: str,
) -> None:
    """Serial and explicit thread requests do not depend on main metadata."""
    monkeypatch.setattr(
        executors,
        '_spawn_incompatibility_reason',
        lambda: pytest.fail('Unexpected spawn probe'),
    )
    assert not executors.can_use_b3_processes(
        count,
        workers,
        processing_mode=ProcessingModeEnumB3(mode),
        executor_backend=backend,
    )


@pytest.mark.integration
def test_incompatible_process_preflight_keeps_serial_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ineligible contexts validate every source without creating a pool."""
    for year in (2023, 2024):
        write_cotahist_txt(
            tmp_path, year=year, records=[build_cotahist_record(year=year)]
        )
    expected = resolve_cotahist_sources(tmp_path)
    monkeypatch.setitem(
        sys.modules, '__main__', SimpleNamespace(__spec__=None)
    )
    monkeypatch.setattr(preflight, '_MIN_PREFLIGHT_SOURCE_BYTES', 1)
    monkeypatch.setattr(
        preflight.ResourcePolicyB3, 'worker_limit', lambda _self, _count: 2
    )
    monkeypatch.setattr(
        preflight,
        'create_b3_executor',
        lambda *_a, **_kw: pytest.fail(
            'Ineligible preflight created an executor'
        ),
    )
    assert (
        preflight.resolve_extraction_sources(
            tmp_path, executor_backend='process'
        )
        == expected
    )


@pytest.mark.integration
@pytest.mark.parametrize('daemon', [False, True])
def test_public_default_reports_actual_thread_backend_in_incompatible_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, daemon: bool
) -> None:
    """Runtime incompatibility is decided before submitting real file work."""
    for year in (2023, 2024):
        write_cotahist_txt(
            tmp_path, year=year, records=[build_cotahist_record(year=year)]
        )
    monkeypatch.delenv('GDF_B3_EXECUTOR_BACKEND', raising=False)
    monkeypatch.setitem(
        sys.modules, '__main__', SimpleNamespace(__spec__=None)
    )
    monkeypatch.setattr(
        executors.mp, 'current_process', lambda: SimpleNamespace(daemon=daemon)
    )
    monkeypatch.setattr(
        preflight.ResourcePolicyB3, 'worker_limit', lambda _self, _count: 2
    )
    client = HistoricalQuotesB3()
    result = client.extract(
        str(tmp_path), initial_year=2023, last_year=2024, verbose=False
    )
    assert result['success'] is True
    assert result['integrity']['verified_rows'] == 2
    assert client.last_phase_timings['effective_backend'] == 'thread'
    assert client.last_phase_timings['effective_worker_limit'] == 2
