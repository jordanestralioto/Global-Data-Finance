"""Worker-limit and pressure-admission behavior for B3 extraction."""

from typing import cast

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from globaldatafinance.core import ResourceMonitor, ResourceState

pytestmark = pytest.mark.unit


class _Monitor:
    """Deterministic resource-state probe for policy tests."""

    def __init__(self, states: list[ResourceState]) -> None:
        self.states = states
        self.calls = 0

    def check_resources(self) -> ResourceState:
        """Return each configured state before holding the final state."""
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        return state


def test_fast_worker_limit_is_bounded_by_cpu_memory_and_file_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast mode uses the documented cap of four workers."""
    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.extraction_service.resource_policy.os.cpu_count',
        lambda: 8,
    )
    policy = extraction_service.ResourcePolicyB3(
        ProcessingModeEnumB3.FAST,
        resource_monitor=cast(
            ResourceMonitor, _Monitor([ResourceState.HEALTHY])
        ),
        available_memory_mib=lambda: 6 * 256,
    )

    assert policy.worker_limit(10) == 3
    assert policy.worker_limit(2) == 2


@pytest.mark.parametrize(
    ('configured_limit', 'expected_limit'),
    [('2', 2), ('0', 1), ('invalid', 3)],
)
def test_fast_worker_limit_honors_documented_environment_cap(
    monkeypatch: pytest.MonkeyPatch,
    configured_limit: str,
    expected_limit: int,
) -> None:
    """The optional runtime cap only reduces the normal fast-mode limit."""
    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.extraction_service.resource_policy.os.cpu_count',
        lambda: 8,
    )
    monkeypatch.setenv('GDF_B3_WORKER_LIMIT', configured_limit)
    policy = extraction_service.ResourcePolicyB3(
        ProcessingModeEnumB3.FAST,
        resource_monitor=cast(
            ResourceMonitor, _Monitor([ResourceState.HEALTHY])
        ),
        available_memory_mib=lambda: 6 * 256,
    )

    assert policy.worker_limit(10) == expected_limit


def test_slow_worker_limit_is_always_one() -> None:
    """Slow mode never adds parallel source workers."""
    policy = extraction_service.ResourcePolicyB3(
        ProcessingModeEnumB3.SLOW,
        resource_monitor=cast(
            ResourceMonitor, _Monitor([ResourceState.HEALTHY])
        ),
        available_memory_mib=lambda: 4096,
    )

    assert policy.worker_limit(20) == 1


@pytest.mark.asyncio
async def test_warning_admits_work_without_waiting_or_gc() -> None:
    """Warnings remain observable but do not reject source admission."""
    monitor = _Monitor([ResourceState.WARNING])
    policy = extraction_service.ResourcePolicyB3(
        ProcessingModeEnumB3.FAST,
        resource_monitor=cast(ResourceMonitor, monitor),
    )

    assert await policy.await_admission() is True
    assert monitor.calls == 1


@pytest.mark.asyncio
async def test_exhaustion_rejects_new_source_admission() -> None:
    """Exhaustion stops new source work before it creates a temp artifact."""
    policy = extraction_service.ResourcePolicyB3(
        ProcessingModeEnumB3.FAST,
        resource_monitor=cast(
            ResourceMonitor, _Monitor([ResourceState.EXHAUSTED])
        ),
    )

    assert await policy.await_admission() is False
