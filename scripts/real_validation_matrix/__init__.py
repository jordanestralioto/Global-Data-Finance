"""Public case-matrix contracts for real-validation campaigns."""

from .cases import Source, build_cases
from .manifest import manifest_for

__all__ = ['Source', 'build_cases', 'manifest_for']
