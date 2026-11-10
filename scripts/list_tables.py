"""Every hand-written string table in the plugin, with file and entries.

Run it any time: python3 scripts/list_tables.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def _entries(node) -> list:
    value = node
    if isinstance(node, ast.Call):
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        if name in ("frozenset", "set", "tuple") and node.args:
            value = node.args[0]
        else:
            return []
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        parts = value.elts
    elif isinstance(value, ast.Dict):
        parts = [k for k in value.keys if k is not None]
    else:
        return []
    if parts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in parts):
        return [str(e.value) for e in parts]
    return []


def main() -> int:
    total = 0
    for path in sorted(HERE.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            name = target.id if isinstance(target, ast.Name) else ""
            if not name.isupper():
                continue
            found = _entries(node.value)
            if len(found) >= 2:
                total += len(found)
                head = ", ".join(found[:6])
                more = "" if len(found) <= 6 else ", ... {} more".format(len(found) - 6)
                print("{} {} {} {}".format(path.name, name, len(found), head + more))
    print("")
    print("{} entries across the tables above.".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
