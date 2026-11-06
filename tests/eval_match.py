"""Deterministic matcher evaluation (no LLM, no network beyond harness catalog).

Runs 32 realistic asks + 8 nonsense asks through match.rank against the
live catalog as loaded via tests/harness.py. Prints per-ask top-1/top-3
hit and a final SUMMARY line.

Usage from /home/andres/concierge:
    PYTHONPATH=/home/andres python tests/eval_match.py
    # or: python -m unittest discover -s tests  (this file is not a test module)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

match = harness.load("match")
seams = harness.load("seams")

# (ask, [acceptable entry names]), hit if any acceptable name is in top-3;
# top-1 hits when the first ranked candidate is acceptable.
REALISTIC = [
    ("search my gmail inbox and read emails", ["gmail"]),
    ("what is the weather forecast for today", ["weather"]),
    ("open youtube recommendations in the hermes desktop browser", ["youtube-dock"]),
    ("create a github issue and review pull requests", ["github_app"]),
    ("edit text inside a PDF without changing the layout", ["pdf-surgeon", "tabella"]),
    ("play music and search my spotify playlists", ["spotify"]),
    ("schedule a meeting on my yandex calendar", ["yandex_calendar"]),
    ("browse and edit my obsidian vault notes", ["obsidian-memory"]),
    ("show my kanban boards and cards", ["kanban-empowered", "kanban-gantt", "kanban-graph", "kanban-live-gantt", "kanban-stream"]),
    ("read RSS feeds and discuss articles", ["hermes-rss", "rss-reader", "hermes-newswire"]),
    ("set up speech and voice text to speech so the agent can talk", ["hermes-speech", "kokoro-tts", "breeze-tts"]),
    ("show me live crypto price ticker for bitcoin", ["crypto-prices"]),
    ("list pods and logs in my kubernetes cluster", ["kubernetes"]),
    ("send me a telegram notification when a job finishes", ["telegram-notify"]),
    ("push a reminder to my phone when a task is done", ["pushary", "pushover-hermes-plugin", "done-bell"]),
    ("remember things across sessions with long term memory", ["chronicle", "agentmemory", "hermes-memory-pane", "wicked-memory", "cognee", "entropicmem", "memanto"]),
    ("change the dark theme skin colours of my terminal", ["hermes-themes-pack", "nord-theme", "glass-theme", "minimalist-themes", "claude-code-theme"]),
    ("drive my browser to fetch and extract webpages", ["aside-browser", "browserpaw", "browser-toggle", "jet-browser", "deepseek-search-fetch", "web-search-plus", "pulldown", "tinyfish", "hermes-plugin-chrome-profiles", "linkup", "cloudflare-web-search"]),
    ("summarize a youtube video transcript", ["by2kb", "flashdata-plugin", "vidiq"]),
    ("read scanned pdf with OCR and convert documents", ["tabella"]),
    ("check my home assistant devices and lights", ["homeassistant"]),
    ("notify me on signal when the agent finishes", ["signal-notify"]),
    ("run a scheduled cron task every morning for a briefing", ["hermes-cron", "cron-bulletin", "morning-briefing", "hermes-windows-tasks", "fxmacrodata"]),
    ("transcribe speech audio to text with speech to text", ["hermes-speech", "hermes-soniox", "deepgram-voice", "wyoming-voice-bridge"]),
    ("search the web with live web search", ["brave-search", "parallel-search", "anysearch", "linkup", "web-search-plus", "search1api", "cloudflare-web-search"]),
    ("manage my remarkable notebook library", ["remarkable"]),
    ("share this chat as a pdf export", ["hermes-chat-share"]),
    ("generate an image of a sunrise", ["dashscope-image", "image-utils", "minimax-image", "acedatacloud-media"]),
    ("control spotify playback from the desktop status bar", ["spotify-desktop"]),
    ("track my github repos and issues", ["my-github", "github_app"]),
    ("edit markdown vault notes with wikilinks and a note graph", ["hermes-plexus", "vault-view"]),
    ("play tidal music and manage my tidal playlists", ["tidal"]),
]

NONSENSE = [
    "teach my goldfish to file taxes",
    "bake a quantum cake with unicorn dust",
    "send a pigeon telegram to the moon on a bicycle",
    "what is the meaning of blorp flibberty gibbet",
    "configure my bicycle to sync with satellites for lunch",
    "who won the invisible dragon baking contest",
    "convert my sandwich into a spreadsheet tax form for fish",
    "recommend a plugin to teach fish philosophy at midnight",
]


def main() -> int:
    entries = list(seams.catalog())
    top1 = top3 = 0
    fails = []
    for i, (ask, expected) in enumerate(REALISTIC, 1):
        ranked = match.rank(ask, entries, limit=3)
        names = [c.name for c in ranked]
        hit1 = bool(names) and names[0] in expected
        hit3 = any(n in expected for n in names)
        top1 += hit1
        top3 += hit3
        status = "TOP1" if hit1 else ("TOP3" if hit3 else "MISS")
        if not hit3:
            fails.append((i, ask, expected, names))
        print(f"[{status}] {i:02d} ask={ask!r} expected={expected} got={names}")
    nofit = 0
    for ask in NONSENSE:
        ranked = match.rank(ask, entries, limit=3)
        names = [c.name for c in ranked]
        ok = not names
        nofit += ok
        print(f"[{'NOFIT' if ok else 'LEAK'}] nonsense ask={ask!r} got={names}")
    print(
        f"SUMMARY top1={top1}/{len(REALISTIC)} ({top1/len(REALISTIC):.2f}) "
        f"top3={top3}/{len(REALISTIC)} ({top3/len(REALISTIC):.2f}) "
        f"nofit={nofit}/{len(NONSENSE)} ({nofit/len(NONSENSE):.2f}) "
        f"catalog={len(entries)}"
    )
    if fails:
        print("FAILS:")
        for i, ask, expected, names in fails:
            print(f"  {i:02d} {ask!r} expected={expected} got={names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
