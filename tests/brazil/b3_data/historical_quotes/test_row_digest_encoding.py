"""Verify the persisted canonical digest against an independent vector."""

from __future__ import annotations

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.row_digest import (
    B3OrderedRowDigest,
)

pytestmark = pytest.mark.unit


def test_canonical_digest_encodes_original_bytes_as_base64() -> None:
    """The version 2 vector covers field framing, null, and Base64 bytes."""
    row: list[str | bytes | None] = [''] * 31 + [bytes(range(245))]
    row[16] = None
    digest = B3OrderedRowDigest()

    digest.update(row)

    assert digest.rows == 1
    assert digest.hexdigest() == (
        # pragma: allowlist nextline secret
        'b6787fdcc39c5f60ccf5d873c352b7d3c7aac39386efb85c1be5f7ac44a4b9dd'
    )
