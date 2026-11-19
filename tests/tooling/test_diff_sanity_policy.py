"""Line policies applied by the diff-sanity gate."""

from __future__ import annotations

import pytest

from scripts.diff_sanity_policy import check_bypass_violations

OUTER_ATTRIBUTE = '#' + '[' + 'allow(dead_code)]'
INNER_ATTRIBUTE = '#!' + '[' + 'expect(unused_imports)]'

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('line', [OUTER_ATTRIBUTE, INNER_ATTRIBUTE])
def test_rust_lint_suppression_attributes_are_rejected(line: str) -> None:
    """Outer and inner Rust lint attributes are executable suppressions."""
    errors = check_bypass_violations(line, 'src/lib.rs', 7)

    assert len(errors) == 1
    assert 'Rust lint suppression' in errors[0]


@pytest.mark.parametrize(
    'line',
    [
        'value = compute()  # allow (legacy input)',
        'page = fetch()  # expect(3) results per page',
    ],
)
def test_comments_mentioning_allow_or_expect_are_accepted(line: str) -> None:
    """Prose in a Python comment is not a Rust attribute."""
    assert check_bypass_violations(line, 'src/module.py', 7) == []
