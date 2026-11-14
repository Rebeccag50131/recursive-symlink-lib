# recursive-symlink-lib

Resolves a path containing nested symbolic links to its final real target while detecting resolution cycles.

## Usage

```python
from recursive_symlink_lib import resolve, CycleError

# Follow a chain of symlinks to the real file.
real_path = resolve("/var/www/current")
print(real_path)

# Cycles are reported, not silently truncated.
try:
    resolve("/var/www/loop")
except CycleError as exc:
    print(exc.chain)
```

The public API is exactly:

- `resolve(path, max_links=40, backend=None) -> str`
- `ResolutionError` (base class)
- `CycleError(path, chain)`
- `TooManyLinksError(path, max_links)`

`resolve` returns a normalized absolute path.  If the final target does
not exist, the returned path is the normalized absolute path the links
point at; a missing target is not an error, because the caller may be
resolving a path before creating it.

## Why this exists

`os.path.realpath` resolves symlink chains but silently stops on cycles
and returns whatever it reached at the cutoff.  That is convenient for
shell-like tooling, but it hides a real problem: if a directory tree
contains a link loop, every downstream operation sees a different
"resolved" path depending on how many hops were allowed.  This library
makes the cycle explicit instead.  The trade-off is that callers who
want the old permissive behaviour must catch `CycleError` and fall back
to `os.path.realpath` themselves.  We think that is the right default:
a cycle is a configuration bug, not a normal condition.

## The awkward edge

Relative symlink targets are resolved against the directory containing
the link, not against the process working directory.  This matches
POSIX and `os.readlink` semantics, but it surprises people who test
with relative paths from a different cwd.  The tests exercise this
explicitly with the in-memory backend so the behaviour is pinned down.

Cycle detection compares normalized absolute paths.  Two links that
reach the same file through different lexical spellings (for example
`/tmp/./a` and `/tmp/a`) are treated as the same path and will be
reported as a cycle if they appear twice in one chain.  We chose lexical
normalization rather than `os.path.realpath` because the latter would
re-introduce the very cycle-truncation we are trying to avoid.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

