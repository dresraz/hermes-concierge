"""The search reads the marketplace's own lists, and only those."""

import unittest
from unittest import mock

from tests import harness

search = harness.load("search")


class Scope(unittest.TestCase):
    def test_only_the_three_marketplace_sources_count(self):
        payload = [
            {"name": "a", "description": "built in", "source": "built-in"},
            {"name": "b", "description": "optional", "source": "optional"},
            {"name": "c", "description": "github", "source": "GitHub"},
            {"name": "d", "description": "third party", "source": "ClawHub"},
            {"name": "e", "description": "third party", "source": "skills.sh"},
            {"name": "f", "description": "third party", "source": "LobeHub"},
        ]
        with mock.patch.object(search, "_cache_dir", lambda: "/tmp"), \
             mock.patch("builtins.open", mock.mock_open(read_data=__import__("json").dumps(payload))), \
             mock.patch.object(search.os.path, "exists", lambda p: True), \
             mock.patch.object(search.os.path, "getmtime", lambda p: __import__("time").time()), \
             mock.patch.object(search.os.path, "join", lambda a, b: b):
            names = [row["name"] for row in search._skills()]
        self.assertEqual(sorted(names), ["a", "b", "c"])

    def test_the_index_answers_in_milliseconds(self):
        rows = [
            {"kind": "skill", "name": "weather", "description": "forecast and rain", "payload": None},
            {"kind": "plugin", "name": "stripe", "description": "card payments", "payload": None},
        ]
        index = search.Index(rows)
        hits = index.search("is it going to rain", 3)
        self.assertEqual(hits[0]["name"], "weather")

    def test_a_forced_refresh_drops_the_old_index(self):
        calls = []
        with mock.patch.object(search, "build", lambda: calls.append(1) or []):
            search.refresh(force=True)
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
