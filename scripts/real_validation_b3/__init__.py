"""Public executor contract for real COTAHIST validation."""

from .artifact_validation import B3_SCHEMA
from .executor import execute_cotahist_case

__all__ = ['B3_SCHEMA', 'execute_cotahist_case']
