"""A long-lived chat must pick up the package that is on disk now."""

from __future__ import annotations

import pathlib
import time
import unittest

import harness


class Reload(unittest.TestCase):
    def setUp(self):
        self.bootstrap = harness.load("_bootstrap")

    def test_a_touched_file_reloads_the_package(self):
        first = self.bootstrap._current()
        path = pathlib.Path(first.__file__)
        stat = path.stat()
        # A written file, exactly as a shipped fix would look to this process.
        path.write_text(path.read_text())
        time.sleep(0.01)
        path.touch()
        try:
            second = self.bootstrap._current()
        finally:
            path.touch()
        self.assertIsNot(first, second)
        self.assertEqual(stat.st_size, path.stat().st_size)

    def test_an_untouched_package_keeps_its_module(self):
        first = self.bootstrap._current()
        self.assertIs(first, self.bootstrap._current())


if __name__ == "__main__":
    unittest.main()
