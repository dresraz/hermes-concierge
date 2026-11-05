"""Recall check that nobody hand-tuned: ask each plugin's own title back.

`eval_match.py` uses hand-written asks, so its numbers can be nudged by editing
the expected lists. This one cannot: it samples the catalog with a fixed seed,
turns each sampled entry's title into the ask, and checks whether the matcher
puts that entry back in the top 3. It is deliberately easy (the title is the
entry's own words), so it measures the floor, not the ceiling.

Usage from /home/andres/concierge:
    PYTHONPATH=/home/andres python tests/eval_recall.py [sample_size]
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

match = harness.load("match")
seams = harness.load("seams")

SAMPLE = 120
SEED = 11


def main(argv: list) -> int:
    size = int(argv[1]) if len(argv) > 1 else SAMPLE
    entries = list(seams.catalog())
    pool = sorted(entries, key=lambda e: str(getattr(e, "name", "")))
    sampled = random.Random(SEED).sample(pool, min(size, len(pool)))

    top1 = top3 = 0
    missed = []
    for entry in sampled:
        name = str(getattr(entry, "name", ""))
        title = str(getattr(entry, "title", "") or name)
        ask = title.strip().lower().rstrip(".")
        if not ask:
            continue
        names = [c.name for c in match.rank(ask, entries, limit=3)]
        if names[:1] == [name]:
            top1 += 1
        if name in names:
            top3 += 1
        else:
            missed.append((ask, name, names))

    total = len(sampled)
    print(f"RECALL top1={top1}/{total} ({top1 / total:.2f}) "
          f"top3={top3}/{total} ({top3 / total:.2f}) catalog={len(entries)}")
    for ask, name, names in missed[:15]:
        print(f"  missed ask={ask!r} want={name} got={names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
