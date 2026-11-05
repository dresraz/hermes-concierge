"""End-to-end install proof against a live catalog entry.

The install path clones from the network and runs the security scan, so it
cannot live in the default suite. It is gated behind CONCIERGE_E2E=1 and it
runs against a throwaway HERMES_HOME so the real agent home is never touched.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

seams = harness.load("seams")

PLUGIN_NAME = "hermes-themes-pack"
MISSING_NAME = "no-such-plugin-xyz"


def _under(child: Path, parent: Path) -> bool:
    # Symlink resolution keeps the containment check honest on any host.
    child_real = Path(os.path.realpath(child))
    parent_real = Path(os.path.realpath(parent))
    return child_real == parent_real or parent_real in child_real.parents


def _file_count(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


@unittest.skipUnless(
    os.environ.get("CONCIERGE_E2E") == "1",
    "CONCIERGE_E2E=1 enables the live network install test",
)
class InstallEndToEnd(unittest.TestCase):
    def setUp(self):
        self._previous_home = os.environ.get("HERMES_HOME")
        self._home = tempfile.mkdtemp(prefix="concierge-e2e-")
        os.environ["HERMES_HOME"] = self._home
        # Core reads HERMES_HOME at call time, but a pinned profile can
        # override it, so confirm the redirect landed before any write.
        try:
            from hermes_constants import get_hermes_home
        except Exception as exc:  # a host without core cannot run this test
            self.skipTest(f"Hermes core is not importable here: {exc}")
        resolved = Path(get_hermes_home())
        if not _under(resolved, Path(self._home)):
            self.skipTest(
                f"core did not honour HERMES_HOME (resolved {resolved}, expected under "
                f"{self._home}); refusing to touch the real home"
            )

    def tearDown(self):
        if self._previous_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._previous_home
        shutil.rmtree(self._home, ignore_errors=True)

    def test_real_catalog_entry_installs_into_the_temp_home(self):
        entries = seams.catalog()
        self.assertTrue(entries, "live catalog returned no entries")
        entry = seams.find(PLUGIN_NAME, entries)
        self.assertIsNotNone(entry, f"{PLUGIN_NAME} is no longer in the live catalog")

        outcome = seams.install(entry)

        self.assertTrue(outcome.ok, f"install did not succeed: {outcome.blocked_reason}")
        self.assertEqual(outcome.installed_name, PLUGIN_NAME)
        self.assertIn(outcome.verdict, {"safe", "caution"})
        self.assertTrue(outcome.enabled, f"plugin was not enabled: {outcome.notes}")

        target = Path(outcome.target)
        self.assertTrue(
            _under(target, Path(self._home)),
            f"install landed outside the temp home: {target}",
        )
        self.assertTrue(target.exists(), f"install target does not exist: {target}")
        self.assertGreaterEqual(
            _file_count(target), 20, f"install target holds too few files: {target}"
        )

    def test_find_reports_none_for_a_name_that_does_not_exist(self):
        entries = seams.catalog()
        self.assertIsNone(seams.find(MISSING_NAME, entries))


if __name__ == "__main__":
    unittest.main()
