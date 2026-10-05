"""Error types for the independent COTAHIST oracle."""

from __future__ import annotations


class OracleMismatch(AssertionError):
    """Identify a raw-source or published-artifact disagreement."""
