import os
import tempfile
import unittest

from recursive_symlink_lib import (
    CycleError,
    TooManyLinksError,
    resolve,
)


class FakeFs:
    """A tiny in-memory filesystem for deterministic tests.

    Paths are stored as given; the backend normalizes them the same way
    the resolver does, so tests can use relative-looking names without
    worrying about the real cwd.
    """

    def __init__(self):
        self.links = {}
        self.files = set()

    def link(self, path, target):
        self.links[os.path.abspath(path)] = target
        return self

    def file(self, path):
        self.files.add(os.path.abspath(path))
        return self

    def __call__(self, path):
        key = os.path.abspath(path)
        if key in self.links:
            return ("link", self.links[key])
        if key in self.files:
            return ("other", None)
        return ("missing", None)


class ResolveWithFakeFsTests(unittest.TestCase):
    def test_plain_file_is_returned_normalized(self):
        fs = FakeFs().file("/tmp/plain.txt")
        got = resolve("/tmp/plain.txt", backend=fs)
        self.assertEqual(got, os.path.normpath("/tmp/plain.txt"))

    def test_missing_path_is_returned_normalized(self):
        fs = FakeFs()
        got = resolve("/tmp/nope", backend=fs)
        self.assertEqual(got, os.path.normpath("/tmp/nope"))

    def test_single_absolute_link(self):
        fs = FakeFs().link("/tmp/a", "/tmp/b").file("/tmp/b")
        self.assertEqual(resolve("/tmp/a", backend=fs), os.path.normpath("/tmp/b"))

    def test_relative_link_is_resolved_against_link_directory(self):
        fs = (
            FakeFs()
            .link("/tmp/dir/a", "b")
            .file("/tmp/dir/b")
        )
        self.assertEqual(
            resolve("/tmp/dir/a", backend=fs),
            os.path.normpath("/tmp/dir/b"),
        )

    def test_chain_of_links(self):
        fs = (
            FakeFs()
            .link("/tmp/a", "/tmp/b")
            .link("/tmp/b", "/tmp/c")
            .file("/tmp/c")
        )
        self.assertEqual(resolve("/tmp/a", backend=fs), os.path.normpath("/tmp/c"))

    def test_cycle_raises_cycle_error_with_chain(self):
        fs = (
            FakeFs()
            .link("/tmp/a", "/tmp/b")
            .link("/tmp/b", "/tmp/a")
        )
        with self.assertRaises(CycleError) as cm:
            resolve("/tmp/a", backend=fs)
        self.assertIn("/tmp/a", cm.exception.chain)
        self.assertIn("/tmp/b", cm.exception.chain)

    def test_self_cycle_raises_cycle_error(self):
        fs = FakeFs().link("/tmp/a", "/tmp/a")
        with self.assertRaises(CycleError):
            resolve("/tmp/a", backend=fs)

    def test_max_links_is_enforced(self):
        fs = FakeFs()
        for i in range(10):
            fs.link("/tmp/l{}".format(i), "/tmp/l{}".format(i + 1))
        fs.file("/tmp/l10")
        with self.assertRaises(TooManyLinksError):
            resolve("/tmp/l0", max_links=3, backend=fs)

    def test_max_links_allows_exact_boundary(self):
        fs = (
            FakeFs()
            .link("/tmp/a", "/tmp/b")
            .link("/tmp/b", "/tmp/c")
            .file("/tmp/c")
        )
        # Two links are followed; max_links=2 must succeed.
        self.assertEqual(
            resolve("/tmp/a", max_links=2, backend=fs),
            os.path.normpath("/tmp/c"),
        )

    def test_invalid_max_links_raises_value_error(self):
        fs = FakeFs()
        with self.assertRaises(ValueError):
            resolve("/tmp/a", max_links=0, backend=fs)

    def test_link_to_missing_target_returns_target_path(self):
        fs = FakeFs().link("/tmp/a", "/tmp/absent")
        self.assertEqual(
            resolve("/tmp/a", backend=fs),
            os.path.normpath("/tmp/absent"),
        )

    def test_relative_chain_through_directory(self):
        fs = (
            FakeFs()
            .link("/tmp/dir/a", "sub/b")
            .link("/tmp/dir/sub/b", "../c")
            .file("/tmp/dir/c")
        )
        self.assertEqual(
            resolve("/tmp/dir/a", backend=fs),
            os.path.normpath("/tmp/dir/c"),
        )


class ResolveWithRealFsTests(unittest.TestCase):
    """A small integration test against the real filesystem.

    The fake backend covers the logic; this test exists to prove the
    default backend actually talks to ``os.lstat``/``os.readlink``.
    """

    def test_real_symlink_chain(self):
        with tempfile.TemporaryDirectory() as td:
            target = os.path.join(td, "target.txt")
            with open(target, "w") as fh:
                fh.write("hello")
            link1 = os.path.join(td, "link1")
            link2 = os.path.join(td, "link2")
            os.symlink(target, link1)
            os.symlink(link1, link2)
            self.assertEqual(resolve(link2), os.path.normpath(target))

    def test_real_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a")
            b = os.path.join(td, "b")
            os.symlink(b, a)
            os.symlink(a, b)
            with self.assertRaises(CycleError):
                resolve(a)


if __name__ == "__main__":
    unittest.main()
