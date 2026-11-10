"""Recursive symlink resolution with cycle detection.

This package exposes a single public entry point, :func:`resolve`, which
follows nested symbolic links until a real file (or a missing target) is
reached.  Resolution cycles are reported explicitly instead of being
silently truncated, because a cycle is almost always a bug in the
caller's directory layout rather than a benign condition.
"""

from .core import (
    ResolutionError,
    CycleError,
    TooManyLinksError,
    resolve,
)

__all__ = [
    "ResolutionError",
    "CycleError",
    "TooManyLinksError",
    "resolve",
]
