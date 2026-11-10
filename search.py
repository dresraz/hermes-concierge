"""The marketplace lists, read as published, never invented.

Two published files: the skills list and the plugin catalog. One small cache
each under the active home, rebuilt only when the source changes or a day has
passed. Queries are plain token overlap. The model orders and names; this file
only counts and ranks lexically for the offline fallback.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

SKILLS_URL = "https://hermes-agent.nousresearch.com/docs/api/skills.json"
PLUGINS_URL = "https://hermes-agent.nousresearch.com/docs/api/plugin-catalog.json"

DAY = 24 * 60 * 60


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(str(get_hermes_home()))
    except Exception:
        import os

        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def _cache_dir() -> Path:
    directory = _home() / "cache" / "concierge"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return directory


def _load(url: str, filename: str) -> list:
    cache = _cache_dir() / filename
    rows: list = []
    checked = 0.0
    try:
        meta = json.loads(cache.read_text()) if cache.exists() else {}
        rows = meta.get("rows") or []
        checked = float(meta.get("checked_at") or 0)
    except Exception:
        rows = []
    if rows and (time.time() - checked) < DAY:
        return rows
    try:
        request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "hermes-concierge"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            try:
                import gzip

                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            except Exception:
                pass
            payload = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return rows
    items = payload if isinstance(payload, list) else (
        payload.get("skills") or payload.get("entries") or payload.get("plugins") or []
    ) if isinstance(payload, dict) else []
    fresh: list = []
    keep_official = filename == "skills-meta.json"
    seen: set = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 100:
            continue
        source = str(item.get("source") or "marketplace")
        if keep_official and source not in ("built-in", "optional", "GitHub"):
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        fresh.append({
            "name": name,
            "description": str(item.get("description") or item.get("overview") or "")[:300],
            "source": source,
        })
    if fresh:
        try:
            cache.write_text(json.dumps({"checked_at": time.time(), "rows": fresh}))
        except Exception:
            pass
        return fresh
    return rows


def skills() -> list:
    rows = _load(SKILLS_URL, "skills-meta.json")
    for row in rows:
        row.setdefault("kind", "skill")
    return rows


def plugins() -> list:
    rows = _load(PLUGINS_URL, "plugins-meta.json")
    for row in rows:
        row.setdefault("kind", "plugin")
    return rows


def connectors() -> list:
    try:
        from tools.connectors.targets import hosted_names

        names = hosted_names() or set()
    except Exception:
        names = set()
    return [{"name": name, "description": "", "source": "connector", "kind": "connector"} for name in sorted(names)]


def counts() -> tuple:
    return (len(skills()), len(plugins()), len(connectors()))


def _tokens(text: str) -> set:
    from . import text as text_mod

    folded = set()
    for word in text_mod.words(text):
        folded.add(word)
        if len(word) > 4 and word.endswith("es"):
            folded.add(word[:-2])
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            folded.add(word[:-1])
        if len(word) >= 6:
            folded.add(word[:5])
    return folded


def candidates(query: str, limit: int = 200) -> list:
    wanted = _tokens(query)
    if not wanted:
        return []
    scored: list = []
    seen: set = set()
    for row in skills() + plugins() + connectors():
        key = row["name"].lower()
        if key in seen or len(key) > 100:
            continue
        seen.add(key)
        name_words = _tokens(row["name"].replace("-", " "))
        hay = name_words | _tokens(row.get("description", ""))
        shared = wanted & hay
        if not shared:
            continue
        weight = sum(len(term) for term in shared)
        name_hits = len(shared & name_words)
        for term in wanted:
            if len(term) >= 4 and any(term in word or word in term for word in name_words):
                name_hits += 1
                break
        scored.append((weight, len(shared), name_hits, row["name"], row))
    scored.sort(key=lambda entry: (-entry[0], -entry[1], -entry[2], entry[3]))
    return [entry[4] for entry in scored[:limit]]


def names_for_model(query: str, limit: int = 200) -> list:
    lines = []
    for row in candidates(query, limit=limit):
        desc = " ".join(str(row.get("description", "") or "").split()[:10])
        if desc:
            lines.append("{} -- {}".format(row["name"], desc))
        else:
            lines.append(row["name"])
    return lines
