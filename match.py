"""Turn one sentence into a shortlist from the live catalog.

Pure functions over a list of catalog entries, so the ranking is testable
without core and the card can explain itself: every candidate carries the
words that earned it its place.

The vocabulary map is the only hand written knowledge in the plugin. It
exists because people ask for outcomes ("remember this forever") while the
catalog is written in mechanisms ("memory provider", "context engine"), and
without the bridge a sentence scores zero against the thing it wants.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Words that carry no signal against a catalog description.
STOPWORDS = frozenset(
    """
    a an and are as at be by can could do does for from get got have how i if
    in into is it its just like me my need of on or our please so some tell
    than that the their them then there these they this to too use using want
    was way we what when where which who will with would you your
    add build create give install installed installing make makes making new
    something anything thing things bot bots agent agents
    skill skills plugin plugins tool tools extension extensions app apps
    look looking help helping job work working properly yourself myself
    """.split()
)

# Outcome words people use, mapped to the words the catalog uses. Values are
# added to the query, never to the entry, so an entry is never rewarded for
# vocabulary it does not have.
VOCABULARY = {
    "remember": ["memory", "recall", "notes", "context"],
    "remembering": ["memory", "recall"],
    "memorize": ["memory", "recall"],
    "forget": ["memory", "recall"],
    "recall": ["memory"],
    "notes": ["note"],
    "brain": ["memory"],
    "colors": ["theme", "skin", "palette"],
    "colour": ["theme", "skin", "palette"],
    "colours": ["theme", "skin", "palette"],
    "look": ["theme", "skin"],
    "looks": ["theme", "skin"],
    "pretty": ["theme", "skin"],
    "skin": ["theme"],
    "dark": ["theme", "palette"],
    "scrape": ["browser", "fetch", "web", "extract"],
    "scraping": ["browser", "fetch", "web"],
    "browse": ["browser"],
    "website": ["web", "browser", "fetch"],
    "speak": ["voice", "tts", "speech"],
    "talk": ["voice", "tts"],
    "audio": ["voice", "tts"],
    "spreadsheet": ["excel", "xlsx", "csv", "sheet"],
    "spreadsheets": ["excel", "xlsx", "csv", "sheet"],
    "deck": ["slide", "presentation", "pptx", "powerpoint"],
    "slides": ["slide", "presentation", "pptx", "powerpoint"],
    "lights": ["home", "lamp", "light"],
    "lamp": ["light", "home"],
    "thermostat": ["home", "climate", "temperature"],
    "invoice": ["pdf", "billing", "document"],
    "contract": ["pdf", "document"],
    "receipt": ["pdf", "expense", "document"],
    "video": ["youtube", "transcript", "mp4"],
    "podcast": ["audio", "transcript", "rss"],
    "news": ["rss", "feed", "monitor"],
    "site": ["web", "hosting", "deploy"],
    "website": ["web", "hosting", "deploy"],
    "prices": ["price", "monitor", "stock"],
    "stocks": ["stock", "market"],
    "inbox": ["email", "mail", "gmail"],
    "calendar": ["calendar", "event", "schedule"],
    "song": ["music"],
    "songs": ["music"],
    "picture": ["image", "vision", "generate"],
    "pictures": ["image", "vision"],
    "photo": ["image", "vision"],
    "draw": ["image", "generate"],
    "code": ["coding", "developer", "repo"],
    "coding": ["coding", "developer"],
    "repo": ["git", "github", "repository"],
    "calendar": ["calendar", "events", "schedule"],
    "schedule": ["calendar", "cron", "schedule"],
    "remind": ["calendar", "cron", "reminder", "notification"],
    "reminder": ["calendar", "cron", "reminder", "notification"],
    "email": ["mail", "smtp", "inbox"],
    "database": ["sql", "database", "query"],
    "search": ["search", "web"],
    "notify": ["notification", "alert"],
    "notifies": ["notification", "alert"],
    "notification": ["notify", "alert"],
    "notifications": ["notify", "alert"],
    "alert": ["notification"],
    "finish": ["notification", "complete", "done"],
    "finished": ["notification", "complete", "done"],
    "done": ["notification", "remind"],
    "push": ["notification", "reminder"],
    "transcribe": ["transcript", "speech", "text"],
    "transcript": ["transcript", "summary"],
    "transcripts": ["transcript", "summary"],
    "summarize": ["summary", "transcript"],
    "summary": ["summary", "transcript"],
    "stt": ["speech", "text"],
    "tts": ["speech", "voice"],
    "generate": ["image", "generation"],
    "generation": ["image", "generate"],
    "cluster": ["kubernetes"],
    "fetch": ["page", "web"],
    "extract": ["page", "web"],
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Weights. A capability that does the job beats a name that merely mentions the
# word: an entry whose tools do X should win over one whose name contains X.
W_NAME = 3.0
W_DESCRIPTION = 1.0
W_CAPABILITY = 4.0
W_PHRASE = 5.0
W_EXACT_NAME = 20.0
W_TIER = 1.0

PREFERRED_TIERS = frozenset({"official", "core", "verified", "safe"})

# Below this the card says nothing fits. A confident wrong install is worse
# than an honest "I did not find anything", so the score floor is paired
# with the earned-word rule below: two substantive matched words are required
# for ordinary multi-word asks, which is what stops a single coincidental
# brand word from looking like a fit.
MIN_SCORE = 1.5
# Below this, a lead only counts when the ask's own words appear in the entry's
# name or title. At 2.0 the whole catalog ties on filler ("general assistant"
# scored 2.05 for a Czech language pack), and a tie is not a recommendation.
STRONG_SCORE = 3.0

# How rare a matched word must be to count towards the earned-word rule.
# A word in nearly every description ("plugin", "the") cannot earn a slot;
# only words that actually discriminate count.
EARN_WORTH = 0.25

# An entry that needs an API key the user has not set is skipped when a usable
# entry scores within this many points of it. The point is that a decisive
# lead still keeps the entry: a plugin that is the only fit is never hidden.
ENV_MARGIN = 2.0


@dataclass
class Candidate:
    name: str
    title: str
    score: float
    matched: list = field(default_factory=list)
    entry: Any = None

    @property
    def description(self) -> str:
        return str(getattr(self.entry, "description", "") or "")

    @property
    def category(self) -> str:
        return str(getattr(self.entry, "category", "") or "")

    @property
    def tier(self) -> str:
        return str(getattr(self.entry, "tier", "") or "")

    def why(self, limit: int = 3) -> str:
        """The words that earned this candidate its place, in the query's order."""
        if not self.matched:
            return "only candidate"
        shown = self.matched[:limit]
        return ", ".join(shown)


def tokens(text: str) -> list:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def _fold(word: str) -> str:
    """One plural rule, applied to both sides: themes and theme are one word."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _joined(query: str) -> list:
    """Adjacent words are often one product name: home assistant -> homeassistant."""
    words = [w for w in _TOKEN_RE.findall((query or "").lower())]
    return [a + b for a, b in zip(words, words[1:]) if len(a) > 2 and len(b) > 2]


def expand(query: str) -> list:
    """The query's words plus the mechanism words they translate into."""
    words = tokens(query)
    seen = dict.fromkeys(words)
    # A product written as two words still has to reach the entry spelled as
    # one: "home assistant" finds homeassistant.
    for joined in _joined(query):
        seen.setdefault(joined, None)
    for word in words:
        for extra in VOCABULARY.get(word, ()):  # ordered, so results stay stable
            seen.setdefault(extra, None)
        # tokens() folds plurals, so "colors" arrives as "color": the same
        # translation has to work for the folded spelling too.
        for extra in VOCABULARY.get(_fold(word), ()):
            seen.setdefault(extra, None)
    return list(seen)


CAPABILITY_KEYS = (
    "provides_tools",
    "provides_hooks",
    "provides_middleware",
    "provides_commands",
    "requires_env",
)


def capabilities(entry: Any) -> dict:
    """The entry's capabilities as a plain dict, whichever shape the catalog hands us.

    The live catalog carries a CatalogCapabilities dataclass; tests and older
    snapshots carry a dict. Both mean the same thing, so both are accepted here
    instead of one shape quietly scoring zero.
    """
    caps = getattr(entry, "capabilities", None)
    if not caps:
        return {}
    if isinstance(caps, dict):
        return {k: v for k, v in caps.items() if v}
    return {k: getattr(caps, k) for k in CAPABILITY_KEYS if getattr(caps, k, None)}


def _entry_tokens(entry: Any) -> tuple:
    name_words = {_fold(t) for t in tokens(str(getattr(entry, "name", "")).replace("-", " "))}
    title_words = {_fold(t) for t in tokens(str(getattr(entry, "title", "")))}
    description_words = {_fold(t) for t in tokens(str(getattr(entry, "description", "")))}
    caps = capabilities(entry)
    cap_text = " ".join(str(v) for v in caps.values() if isinstance(v, (list, tuple)))
    cap_text += " " + " ".join(str(k) for k in caps)
    category = {_fold(t) for t in tokens(str(getattr(entry, "category", "")))}
    return (
        name_words,
        title_words,
        description_words,
        {_fold(t) for t in tokens(cap_text)},
        category,
    )


def word_weights(entries: Iterable[Any]) -> dict:
    """How much each word is worth, from how rare it is in the catalog.

    A word every plugin mentions says nothing about which one you want, so
    "read" scores near zero while "webpage" scores high. The value is a share
    between 0 and 1, not a raw count, so the same thresholds hold whether the
    catalog has 3 entries or 977. This is the only thing standing between an
    honest "nothing fits" and installing a calendar plugin because it happens
    to contain the verb read.
    """
    total = 0
    seen = {}
    for entry in entries:
        total += 1
        words = set()
        for group in _entry_tokens(entry):
            words |= group
        for word in words:
            seen[word] = seen.get(word, 0) + 1
    if not total:
        return {}
    reach = math.log(1.0 + total)
    return {
        word: math.log(1.0 + total / (1.0 + df)) / reach
        for word, df in seen.items()
    }


def score(query: str, entry: Any, weights: Optional[dict] = None) -> Candidate:
    """Score one entry against one sentence."""
    asked = expand(query)
    name_words, title_words, description_words, cap_words, category_words = _entry_tokens(entry)

    total = 0.0
    matched = []
    seen = set()
    for word in asked:
        key = _fold(word)
        if key in seen:
            continue
        worth = (
            weights.get(key, 1.0)
            if weights is not None
            else 1.0
        )
        # Past twelve words a description is a keyword dump, not a description:
        # a plugin that names everything must not beat one that names the ask.
        worth = worth if len(seen) < 12 else worth * 0.6
        hit = False
        if key in name_words or key in title_words:
            total += W_NAME * worth
            hit = True
        if key in cap_words:
            total += W_CAPABILITY * worth
            hit = True
        if key in description_words:
            total += W_DESCRIPTION * worth
            hit = True
        if key in category_words:
            total += W_CAPABILITY * worth
            hit = True
        if hit:
            seen.add(key)
            matched.append(word)

    name = str(getattr(entry, "name", ""))
    phrase = " ".join(tokens(query))
    if phrase and len(phrase) > 3 and phrase in f"{name} {getattr(entry, 'title', '')}".lower():
        total += W_PHRASE

    # Names are often two words run together ("homeassistant"); a two-word
    # query whose concatenation is the plugin name is the same signal.
    query_tokens = tokens(query)
    name_token_words = name_words | title_words
    for a, b in zip(query_tokens, query_tokens[1:]):
        if _fold(a) + _fold(b) in name_token_words:
            total += W_PHRASE
            break

    lowered_query = query.lower()
    if name and (name == lowered_query.strip() or name.replace("-", " ") == lowered_query.strip()):
        total += W_EXACT_NAME

    if matched and str(getattr(entry, "tier", "")).lower() in PREFERRED_TIERS:
        total += W_TIER

    ordered = [w for w in dict.fromkeys(asked) if w in matched]
    return Candidate(
        name=name,
        title=str(getattr(entry, "title", "") or name),
        score=total,
        matched=ordered,
        entry=entry,
    )


def _earned(candidate: Candidate, weights: dict, query_tokens: int = 0) -> bool:
    """Whether a candidate did more than catch one generic word.

    One verb like "read" appears in hundreds of descriptions, so a single
    match proves nothing. Either two substantive query words landed, or this
    was a short query naming the plugin itself: a one-word ask like "kubernetes"
    is allowed to match by name alone, while a longer sentence is not, because
    a longer sentence that only catches one brand word is a coincidence.
    """
    substantive = [
        word
        for word in candidate.matched
        if weights.get(_fold(word), 1.0) >= EARN_WORTH
    ]
    if len(substantive) >= 3:
        return True
    if len(substantive) == 2:
        # Two words in a long sentence is usually a coincidence: "convert my
        # sandwich into a spreadsheet tax form for fish" caught "form" and
        # "fish". A short ask still earns its place on two words.
        return query_tokens < 6
    if not substantive:
        return False
    if query_tokens > 3:
        return False
    word = _fold(substantive[0])
    name_words, title_words = _entry_tokens(candidate.entry)[:2]
    return word in (name_words | title_words) and weights.get(word, 0.0) >= 0.3


def _missing_env(candidate: Candidate) -> bool:
    """True when a required key is not set in the environment.

    An empty value counts as unset. An entry whose requires_env cannot be
    read is treated as having no requirement, so a weird catalog shape never
    hides a plugin by mistake.
    """
    try:
        required = capabilities(candidate.entry).get("requires_env") or ()
    except Exception:
        return False
    if isinstance(required, str):
        required = (required,)
    # Only environment-style names count: catalog snapshots occasionally carry
    # a placeholder like "name", and that is not a key the user can set.
    keys = [
        str(key)
        for key in required
        if key and str(key) == str(key).upper()
    ]
    return any(not os.environ.get(key) for key in keys)


def rank(query: str, entries: Iterable[Any], limit: int = 3) -> list:
    """The best *limit* candidates for *query*, best first, no unearned filler."""
    entries = list(entries)
    weights = word_weights(entries)
    query_tokens = len(tokens(query))
    scored = [score(query, entry, weights) for entry in entries]
    keep = [
        c for c in scored
        if c.score >= MIN_SCORE and _earned(c, weights, query_tokens)
    ]
    # A plugin this user cannot run loses to a usable one that is close,
    # but is never hidden outright: a decisive lead (or being the only
    # candidate) keeps it.
    usable = [c.score for c in keep if not _missing_env(c)]
    if usable:
        best_usable = max(usable)
        keep = [
            c for c in keep
            if not _missing_env(c) or c.score - best_usable > ENV_MARGIN
        ]
    keep.sort(key=lambda c: (-c.score, c.name))
    if keep and keep[0].score < STRONG_SCORE:
        asked = {_fold(word) for word in tokens(query)}
        def named(candidate: Any) -> bool:
            return bool(asked & {_fold(word) for word in tokens(candidate.name + " " + candidate.title)})
        keep = [c for c in keep if c.score >= STRONG_SCORE or named(c)]
    return keep[:limit]


def best(query: str, entries: Optional[Iterable[Any]] = None) -> Optional[Candidate]:
    if entries is None:
        from . import seams

        entries = seams.catalog()
    ranked = rank(query, entries, limit=1)
    return ranked[0] if ranked else None
