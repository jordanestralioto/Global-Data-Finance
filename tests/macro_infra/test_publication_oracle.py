"""The campaign oracle requires the independently observed commit decision."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.publication_campaign import (
    assert_recovered,
    journal_decision,
    prepare_destination,
    traced_decision,
)
from tests.support.publication_crashes import ARTIFACT_NAMES

pytestmark = pytest.mark.unit


def test_completed_rollback_supersedes_an_earlier_commit_attempt() -> None:
    """A handled storage failure may durably roll back before returning."""
    events = [
        {'phase': 'COMMITTED'},
        {'phase': 'ROLLING_BACK'},
        {'phase': 'ROLLED_BACK'},
    ]

    assert traced_decision(events) == 'old'


@pytest.mark.parametrize('committed', [False, True])
def test_absent_journal_retains_observed_commit_decision(
    tmp_path: Path, committed: bool
) -> None:
    """Require old before commit and new after committed cleanup."""
    root = tmp_path / 'destination'
    payloads = tmp_path / 'payloads'
    payloads.mkdir()
    for version in ('old', 'new'):
        for name in ARTIFACT_NAMES:
            (payloads / f'{version}-{name}').write_bytes(version.encode())
    original = prepare_destination(root, payloads, existing=True)
    events = [{'phase': 'COMMITTED' if committed else 'OPEN'}]
    decision = journal_decision(root, fallback=traced_decision(events))
    if committed:
        for name in ARTIFACT_NAMES:
            (root / name).write_bytes(b'new')

    assert decision == ('new' if committed else 'old')
    assert assert_recovered(root, original, payloads, decision=decision) == (
        decision
    )

    for name in ARTIFACT_NAMES:
        (root / name).write_bytes(b'old' if committed else b'new')
    with pytest.raises(AssertionError, match='journal requires'):
        assert_recovered(root, original, payloads, decision=decision)
