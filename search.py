"""Search the whole marketplace: every plugin, connector and skill, ranked locally.

The old matcher scored a hand-picked catalog with hand-written weights. This is a
real index over everything Hermes can install — about 105,000 entries — built once,
cached on disk, and asked in milliseconds. No model, no downloads, no network at
question time.

Ranking is BM25: term frequency, document length, and how rare a word is. That is
the boring, correct answer for "find entries that talk about this", and it does not
need a synonym table to work.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.request
from collections import Counter
from typing import Any, Optional

from . import seams

INDEX_VERSION = 3
INDEX_URL = "https://hermes-agent.nousresearch.com/docs/api/skills.json"

# The Nous marketplace, not the wider skill internet. The published index also
# carries ClawHub, LobeHub and skills.sh; those are 100k third-party skills and
# offering them is how "find recent papers" once answered with a Chinese paper
# site. Only the first-party rows are in scope.
# The sources the marketplace's Skills tab shows. The published index also
# carries ClawHub, LobeHub, skills.sh and browse.sh — 100k third-party skills
# the screen does not list, and a model cannot read. 44 built-in + 141 optional
# + 526 GitHub is the 711 the marketplace shows.
NOUS_SOURCES = frozenset({"built-in", "optional", "GitHub"})

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set(
    """a an and are as at be by can could do does for from get got have how i if in into is it its
    just like me my need of on or our please so some tell than that the their them then there these
    they this to too use using want was way we what when where which who will with would you your
    add build create give install installed installing make makes new something anything thing
    things bot bots agent agents skill skills plugin plugins tool tools extension extensions app
    apps look looking help helping job work working properly yourself myself""".split()
)


def _cache_dir() -> str:
    try:
        from hermes_constants import get_hermes_home

        home = get_hermes_home()
    except Exception:
        home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    path = os.path.join(str(home), "cache", "concierge")
    os.makedirs(path, exist_ok=True)
    return path


def words(text: str) -> list:
    return [w for w in TOKEN.findall((text or "").lower()) if w not in STOP and len(w) > 1]


def fold(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# Enough of a description to know what a thing is; the long tail is the
# difference between 1.6 MB and half that, and nobody picks from paragraph nine.
KEEP = 220


def _clip(text: Any) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:KEEP]


def _entry(kind: str, name: str, description: str, payload: Any = None) -> dict:
    return {"kind": kind, "name": str(name or ""), "description": _clip(description), "payload": payload}


def _read_meta(name: str) -> dict:
    try:
        with open(os.path.join(_cache_dir(), name), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_meta(name: str, meta: dict) -> None:
    try:
        with open(os.path.join(_cache_dir(), name), "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
    except Exception:
        pass


def _json_payload(url: str, etag: str = "") -> tuple:
    """Fetch a published list gzipped, honouring an ETag. None means unchanged."""
    headers = {"Accept-Encoding": "gzip"}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip

                raw = gzip.decompress(raw)
            return json.loads(raw), resp.headers.get("ETag") or ""
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag
        raise


def _skills_meta() -> dict:
    """What we kept last time, and how to tell whether it changed."""
    path = os.path.join(_cache_dir(), "skills-meta.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_skills_meta(meta: dict) -> None:
    try:
        with open(os.path.join(_cache_dir(), "skills-meta.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
    except Exception:
        pass


def _skills_payload(url: str, etag: str = "") -> tuple:
    """The published document, gzipped, never written to disk whole.

    It is 65 MB uncompressed. We read it, keep the 711 rows that matter, and
    throw the rest away. A conditional request costs a few hundred bytes and
    answers "unchanged" without sending the file at all.
    """
    headers = {"Accept-Encoding": "gzip"}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip

                raw = gzip.decompress(raw)
            return json.loads(raw), resp.headers.get("ETag") or ""
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag or ""
        raise


def _skills() -> list:
    """The 711 skills the marketplace's Skills tab lists."""
    meta = _skills_meta()
    rows = meta.get("rows") or []
    checked = float(meta.get("checked_at") or 0)
    # Ask whether it changed at most once a day; a "no" costs a few hundred
    # bytes and the 11 MB only moves when the list really is new.
    if not rows or (time.time() - checked) > 24 * 60 * 60:
        try:
            payload, etag = _skills_payload(INDEX_URL, meta.get("etag", ""))
        except Exception:
            payload, etag = None, meta.get("etag", "")
        if payload is None and rows:
            _write_skills_meta({**meta, "checked_at": time.time()})
        elif payload is not None:
            items = payload if isinstance(payload, list) else (
                payload.get("skills") or payload.get("entries") or []
            ) if isinstance(payload, dict) else []
            rows = [
                {"name": item.get("name", ""), "description": _clip(item.get("description")), "source": item.get("source", "")}
                for item in items
                if isinstance(item, dict) and str(item.get("source") or "") in NOUS_SOURCES
            ]
            _write_skills_meta({"checked_at": time.time(), "etag": etag, "rows": rows})
    return [_entry("skill", r["name"], r.get("description", ""), r) for r in rows]


def _local_skills() -> list:
    """Skills already on this machine: they are part of what can be turned on."""
    out = []
    try:
        from . import discover

        for item in discover.catalogue():
            out.append(_entry("skill", item["name"], item.get("why") or item.get("description") or "", item))
    except Exception:
        pass
    return out


PLUGIN_URL = "https://hermes-agent.nousresearch.com/docs/api/plugin-catalog.json"


def _plugins() -> list:
    """Name and one line per plugin. The 2.4 MB document is read and dropped."""
    meta = _plugins_meta()
    rows = meta.get("rows") or []
    checked = float(meta.get("checked_at") or 0)
    if not rows or (time.time() - checked) > 24 * 60 * 60:
        try:
            payload, etag = _json_payload(PLUGIN_URL, meta.get("etag", ""))
        except Exception:
            payload, etag = None, meta.get("etag", "")
        if payload is not None:
            items = payload if isinstance(payload, list) else (
                payload.get("entries") or payload.get("plugins") or []
            ) if isinstance(payload, dict) else []
            rows = [
                {"name": str(item.get("name") or ""), "description": _clip(item.get("description"))}
                for item in items
                if isinstance(item, dict) and item.get("name")
            ]
            _write_meta("plugins-meta.json", {"checked_at": time.time(), "etag": etag, "rows": rows})
        elif rows:
            _write_meta("plugins-meta.json", {**meta, "checked_at": time.time()})
    return [_entry("plugin", r["name"], r.get("description", ""), r) for r in rows]


def _plugins_meta() -> dict:
    return _read_meta("plugins-meta.json")


def _connectors() -> list:
    """The hosted connectors the marketplace lists, then Hermes's MCP catalog."""
    out = []
    seen = set()
    try:
        from tools.connectors.targets import hosted_names

        for name in sorted(hosted_names() or ()):
            seen.add(str(name).lower())
            out.append(_entry("connector", name, "hosted connector, needs a login", name))
    except Exception:
        pass
    # MCP servers are their own tab in the marketplace, so they are not
    # connectors here: the screen shows 54, and so do we.
    return out


def build() -> list:
    """Every installable thing, from all three registries."""
    hub = _skills()
    local = _local_skills()
    seen = {row["name"].lower() for row in local}
    # Local skills first (already installed), then the marketplace the screen shows.
    return local + [row for row in hub if row["name"].lower() not in seen] + _plugins() + _connectors()


class Index:
    """BM25 over the merged marketplace."""

    def __init__(self, rows: list, k1: float = 1.4, b: float = 0.72):
        self.rows = rows
        self.k1, self.b = k1, b
        self.counts: list = []
        self.lengths: list = []
        df: Counter = Counter()
        for row in rows:
            name_words = [fold(w) for w in words(row["name"].replace("-", " "))]
            body = [fold(w) for w in words(row["description"])][:60]
            # A name is what a person is most likely to say, so it counts thrice.
            counts = Counter(name_words * 3 + body)
            self.counts.append(counts)
            self.lengths.append(sum(counts.values()))
            df.update(counts.keys())
        self.df = df
        self.n = max(len(rows), 1)
        self.avg = sum(self.lengths) / self.n

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, limit: int = 20) -> list:
        terms = [fold(w) for w in words(query)]
        if not terms:
            return []
        scored = []
        for idx, counts in enumerate(self.counts):
            score = 0.0
            for term in terms:
                freq = counts.get(term, 0)
                if not freq:
                    continue
                score += self.idf(term) * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * self.lengths[idx] / self.avg)
                )
            if score > 0:
                scored.append((score, idx))
        scored.sort(reverse=True)
        out = []
        for score, idx in scored[:limit]:
            row = dict(self.rows[idx])
            row["score"] = score
            out.append(row)
        return out


_INDEX: Optional[Index] = None


def stale() -> bool:
    """True when a list is missing. Age is not staleness: the file is the list."""
    if not os.path.exists(os.path.join(_cache_dir(), "skills.json")):
        return True
    try:
        from . import seams

        return not seams._own_catalog_cache().exists()
    except Exception:
        return False


def refresh(force: bool = False) -> bool:
    """Rebuild from the live lists when they are a day old. True if it rebuilt.

    Concierge has three lists and no memory of its own: whatever the marketplace
    publishes is what it can offer. This is the only place that is enforced.
    """
    global _INDEX
    if not force and _INDEX is not None and not stale():
        return False
    if force:
        for name in ("skills.json", "marketplace-skills.json"):
            path = os.path.join(_cache_dir(), name)
            if os.path.exists(path):
                os.remove(path)
    _INDEX = None
    rows = build()
    _INDEX = Index(rows) if rows else Index([])
    return True


def index() -> Index:
    global _INDEX
    if _INDEX is None:
        refresh()
    return _INDEX


def search(query: str, limit: int = 20) -> list:
    """Ranked rows: kind, name, description, score."""
    return index().search(query, limit)


def menu() -> str:
    """Every entry as one line: kind and name. 43k characters for 2,131.

    Small enough to hand a model the whole marketplace, which beats any keyword
    gate: the gate is what hides "weather" from "is it going to rain".
    """
    return "\n".join("{} {}".format(row["kind"], row["name"]) for row in index().rows)


def find(kind: str, name: str) -> Optional[dict]:
    for row in index().rows:
        if row["kind"] == kind and row["name"].lower() == str(name or "").lower():
            return row
    return None
