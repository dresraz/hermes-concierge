"""Live probe: what do real catalog entries declare before the yes?

Read-only. Fetches each plugin's own manifest from its pinned public commit, the
same way the card does, and prints the line the card would show.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

seams = harness.load("seams")

entries = list(seams.catalog())
random.Random(7).shuffle(entries)
sample = entries[:40]

with_deps = []
for entry in sample:
    try:
        deps = seams.declared_deps_remote(entry)
    except Exception as exc:  # noqa: BLE001 - one bad entry must not end the probe
        deps, exc_text = [], f"{type(exc).__name__}: {exc}"
    else:
        exc_text = ""
    if deps:
        with_deps.append((entry.name, deps))
    print(f"{entry.name:<32} {len(deps)} {exc_text} {deps[:3]}")

print(f"\nSUMMARY entries={len(sample)} with_deps={len(with_deps)}")
for name, deps in with_deps:
    print(f"  CARD LINE {name}: {', '.join(str(d) for d in deps)[:150]}")
