"""Record actual pytest outcomes and enforce required release executions."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import pytest

from scripts.check_release_evidence import (
    NATIVE_OPTIONAL_SKIP,
    NATIVE_REQUIRED_CASES,
)

_OUTCOMES: dict[str, str] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    """Declare explicit opt-in release evidence and required case names."""
    group = parser.getgroup('release-evidence')
    group.addoption('--release-evidence', metavar='PATH')
    group.addoption('--release-required-case', action='append', default=[])
    group.addoption('--release-allow-skip', action='append', default=[])
    group.addoption('--release-native', action='store_true')


def pytest_configure() -> None:
    """Start an independent result collection for this pytest process."""
    _OUTCOMES.clear()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Retain failures from setup/teardown and genuine call outcomes."""
    previous = _OUTCOMES.get(report.nodeid)
    if previous == 'failed':
        return
    if (
        report.failed
        or report.skipped
        or (report.when == 'call' and previous != 'failed')
    ):
        _OUTCOMES[report.nodeid] = report.outcome


def evaluate_results(
    collected: list[str],
    outcomes: dict[str, str],
    required: list[str],
    allowed_skips: list[str],
) -> list[str]:
    """Reject empty, unfinished, skipped-critical, or missing test evidence."""
    issues = []
    if not collected or not any(
        value == 'passed' for value in outcomes.values()
    ):
        issues.append('release validation requires executed passing tests')
    for nodeid in collected:
        outcome = outcomes.get(nodeid)
        if outcome is None or outcome == 'failed':
            issues.append(f'case did not pass: {nodeid}')
        elif (
            outcome == 'skipped'
            and nodeid.rsplit('::', 1)[-1] not in allowed_skips
        ):
            issues.append(f'required case was skipped: {nodeid}')
    for name in required:
        matches = [
            nodeid
            for nodeid in collected
            if nodeid.rsplit('::', 1)[-1].split('[', 1)[0] == name
        ]
        if not matches or any(
            outcomes.get(nodeid) != 'passed' for nodeid in matches
        ):
            issues.append(f'required release behavior did not pass: {name}')
    return issues


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write terminal evidence and fail sessions missing required behavior."""
    raw_path = session.config.getoption('--release-evidence')
    if raw_path is None:
        return
    collected = [item.nodeid for item in session.items]
    required = list(session.config.getoption('--release-required-case'))
    allowed = list(session.config.getoption('--release-allow-skip'))
    if session.config.getoption('--release-native'):
        required.extend(NATIVE_REQUIRED_CASES)
        if platform.system() == 'Windows':
            allowed.append(NATIVE_OPTIONAL_SKIP)
    issues = evaluate_results(
        collected,
        _OUTCOMES,
        required,
        allowed,
    )
    passed = exitstatus == 0 and not issues
    report: dict[str, Any] = {
        'kind': 'release-pytest-results',
        'status': 'passed' if passed else 'failed',
        'platform': platform.platform(),
        'system': platform.system(),
        'python': platform.python_version(),
        'collected': collected,
        'outcomes': _OUTCOMES,
        'issues': issues,
        'exit_code': int(exitstatus) if exitstatus else (0 if passed else 1),
    }
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    if not passed:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
