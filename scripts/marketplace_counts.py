"""Print what Concierge loaded, and where each list came from.

Run it, then compare against https://hermes-agent.nousresearch.com/marketplace

    python scripts/marketplace_counts.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collections import Counter  # noqa: E402

from concierge import search  # noqa: E402


def main() -> int:
    rows = search.build()
    kinds = Counter(row["kind"] for row in rows)
    listed = search._skills()
    local = search._local_skills()
    print("source".ljust(12), "count".rjust(6))
    print("-" * 20)
    for kind in ("skill", "plugin", "connector"):
        print(kind.ljust(12), str(kinds.get(kind, 0)).rjust(6))
    print("-" * 20)
    print("total".ljust(12), str(len(rows)).rjust(6))
    print()
    print("skills in the published list:", len(listed))
    print("  already installed here:    ", len(local))
    print("  counted once:              ", kinds.get("skill", 0))
    print()
    print("where:")
    print("  skills     ", search.INDEX_URL)
    print("  plugins    ", __import__("concierge.seams", fromlist=["x"]).LIVE_URL)
    print("  connectors  tools/connectors/targets.py::hosted_names()")
    print()
    print("sample, three per shelf:")
    for kind in ("skill", "plugin", "connector"):
        names = [row["name"] for row in rows if row["kind"] == kind][:3]
        print(" ", kind, "->", ", ".join(names) or "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
