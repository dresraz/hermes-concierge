"""Every hand-written string table in the plugin, with file, line and entries.

Run it any time:  python3 scripts/list_tables.py

It finds module-level constants assigned a tuple/list/set of string literals (any
size, including pairs), plus dicts whose keys are strings. If a decision in this
plugin is made by a list of words, it shows up here.
"""

from __future__ import annotations

import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def _strings(node) -> list:
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("frozenset", "set", "tuple"):
        node = node.args[0] if node.args else None
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        if all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            return [e.value for e in node.elts]
    if isinstance(node, ast.Dict):
        keys = node.keys
        if keys and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in keys):
            return [k.value for k in keys]
    return []


def main() -> int:
    total = 0
    for path in sorted(HERE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            name = getattr(node.targets[0], "id", "")
            if not name.isupper():
                continue
            entries = _strings(node.value)
            if not entries:
                continue
            total += len(entries)
            head = ", ".join(entries[:6])
            more = "" if len(entries) <= 6 else ", … {} more".format(len(entries) - 6)
            print("{:16} {:22} {:3}  {}".format(path.name, name, len(entries), head + more))
    print("\n{} entries across the tables above.".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
