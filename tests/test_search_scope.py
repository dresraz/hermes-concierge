"""The search reads the marketplace's own lists, and only those."""

import unittest
from unittest import mock

from tests import harness

search = harness.load("search")


def payload():
    return {
        "skills": [
            {"name": "a", "description": "built in", "source": "built-in"},
            {"name": "b", "description": "optional", "source": "optional"},
            {"name": "c", "description": "github", "source": "GitHub"},
            {"name": "d", "description": "third party", "source": "ClawHub"},
            {"name": "e", "description": "third party", "source": "skills.sh"},
            {"name": "f", "description": "third party", "source": "LobeHub"},
        ]
    }


class Scope(unittest.TestCase):
    def read(self, doc):
        with mock.patch.object(search, "_skills_meta", lambda: {}), \
             mock.patch.object(search, "_skills_payload", lambda url, etag="": (doc, "etag")), \
             mock.patch.object(search, "_write_skills_meta", lambda meta: None):
            return [row["name"] for row in search._skills()]

    def test_only_the_three_marketplace_sources_count(self):
        self.assertEqual(sorted(self.read(payload())), ["a", "b", "c"])

    def test_a_list_already_on_disk_is_used_without_a_download(self):
        meta = {"checked_at": __import__("time").time(), "etag": "x", "rows": [{"name": "kept", "description": "old"}]}
        calls = []
        with mock.patch.object(search, "_skills_meta", lambda: meta), \
             mock.patch.object(search, "_skills_payload", lambda *a, **k: calls.append(1) or (None, "")):
            names = [row["name"] for row in search._skills()]
        self.assertEqual(names, ["kept"])
        self.assertEqual(calls, [], "a fresh list must not be fetched again")

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
