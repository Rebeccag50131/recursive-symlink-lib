"""Core symlink resolution logic.

The resolver models the filesystem through a small protocol so that the
cycle-detection logic can be tested without touching the real disk.  The
default backend reads the real filesystem with ``os.lstat``/``os.readlink``.

Design decision: we do not use ``os.path.realpath`` because it silently
truncates cycles and, on some platforms, resolves links relative to the
current working directory in ways that are hard to reason about.  We want
the caller to know when a cycle exists.
"""

from __future__ import annotations

import os
from typing import Callable, Optional


class ResolutionError(Exception):
    """Base class for failures while resolving a symlink chain."""


class CycleError(ResolutionError):
    """Raised when the link chain revisits a path."""

    def __init__(self, path: str, chain: list[str]) -> None:
        self.path = path
        self.chain = list(chain)
        # The chain includes the repeated path at the end so callers can
        # print the exact loop without having to reconstruct it.
        super().__init__(
            "symlink cycle detected at {!r}: {}".format(
                path, " -> ".join(self.chain)
            )
        )


class TooManyLinksError(ResolutionError):
    """Raised when a chain exceeds ``max_links`` without resolving."""

    def __init__(self, path: str, max_links: int) -> None:
        self.path = path
        self.max_links = max_links
        super().__init__(
            "exceeded max_links={} while resolving {!r}".format(max_links, path)
        )


# A backend returns one of:
#   ("link", target)  -- path is a symlink pointing at target
#   ("other", None)   -- path exists and is not a symlink
#   ("missing", None) -- path does not exist
#
# Keeping this as a plain tuple rather than a class keeps the fake
# backends in the tests short and obvious.
Backend = Callable[[str], tuple[str, Optional[str]]]


def _real_backend(path: str) -> tuple[str, Optional[str]]:
    """Inspect the real filesystem.

    ``os.lstat`` is used deliberately: ``os.stat`` follows links, which is
    exactly the behaviour we are trying to implement ourselves.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return ("missing", None)
    except NotADirectoryError:
        # A component of the path is not a directory.  Treat it as
        # missing rather than raising, because the caller asked for a
        # resolution and there is nothing to resolve.
        return ("missing", None)
    except OSError:
        return ("missing", None)

    if os.path.stat.S_ISLNK(st.st_mode):
        try:
            target = os.readlink(path)
        except OSError:
            return ("missing", None)
        return ("link", target)
    return ("other", None)


def _normalize(path: str) -> str:
    """Normalize a path for identity comparison.

    Symlink loops are detected by comparing normalized absolute paths.
    We intentionally do not resolve ``..`` against the filesystem here;
    ``os.path.normpath`` is purely lexical, which is the right level for
    cycle detection because a link target is a lexical string.
    """
    return os.path.normpath(os.path.abspath(path))


def resolve(
    path: str,
    max_links: int = 40,
    backend: Optional[Backend] = None,
) -> str:
    """Resolve ``path`` through any chain of symbolic links.

    Returns the normalized absolute path of the final non-symlink target.
    If the final target does not exist, the returned path is still the
    normalized absolute path that the links point at; the caller can
    decide whether a missing target is an error.

    Raises :class:`CycleError` if the chain revisits a path and
    :class:`TooManyLinksError` if more than ``max_links`` links are
    followed.  ``max_links`` defaults to 40, the same limit used by
    ``os.path.realpath`` on most systems.

    ``backend`` exists so tests can supply a deterministic in-memory
    filesystem; production callers should leave it as ``None``.
    """
    if max_links < 1:
        raise ValueError("max_links must be at least 1")

    inspect: Backend = backend if backend is not None else _real_backend

    current = os.path.abspath(path)
    seen: list[str] = []
    seen_set: set[str] = set()

    while True:
        key = _normalize(current)
        if key in seen_set:
            seen.append(current)
            raise CycleError(current, seen)
        seen.append(current)
        seen_set.add(key)

        kind, target = inspect(current)
        if kind != "link":
            return os.path.normpath(current)

        if len(seen) > max_links:
            raise TooManyLinksError(current, max_links)

        assert target is not None  # narrows type for type checkers
        if os.path.isabs(target):
            current = target
        else:
            current = os.path.join(os.path.dirname(current), target)
