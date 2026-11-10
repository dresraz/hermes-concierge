"""Bot presets, as data only.

A preset is a role name, one line about it, and the skills that role starts
with. Nothing here detects anything. The model picks the role from the names
and blurbs. The code installs the list unchanged.
"""

from __future__ import annotations

ROLES: dict = {
    "researcher": {
        "blurb": "reads sources, follows feeds, keeps citations",
        "skills": ["rss-feeds", "literature-review", "arxiv", "grounded-citations", "pdf", "blocked-page-recovery"],
    },
    "writer": {
        "blurb": "finds the angle, writes it plain, illustrates and ships it",
        "skills": ["simple-english", "baoyu-article-illustrator", "publish-site", "humanizer", "creative-ideation"],
    },
    "coder": {
        "blurb": "debugs, searches structure, reviews, documents the repo",
        "skills": ["ast-grep", "code-wiki", "github", "systematic-debugging", "requesting-code-review", "python-debugpy"],
    },
    "assistant": {
        "blurb": "own inbox, calendar, files and notes",
        "skills": ["email-inbox-triage", "google-workspace", "pdf", "document-to-action-items", "meeting-action-items", "teams-meeting-pipeline", "obsidian", "apple-reminders"],
    },
    "marketer": {
        "blurb": "plans campaigns, reads communities, makes the assets",
        "skills": ["social-media-content-calendar", "reddit-reading", "meme-generation", "baoyu-infographic", "creative-ideation"],
    },
    "watcher": {
        "blurb": "polls sources, dedupes, pings you, keeps a board",
        "skills": ["watchers", "rss-feeds", "live-dashboard", "product-price-monitor", "competitor-news-monitor"],
    },
    "designer": {
        "blurb": "mocks, diagrams, tokens, infographics",
        "skills": ["sketch", "excalidraw", "design-md", "claude-design", "baoyu-infographic"],
    },
    "analyst": {
        "blurb": "workbooks, decks, charts, live numbers",
        "skills": ["excel-author", "pptx-author", "stocks", "live-dashboard", "plotly"],
    },
    "tutor": {
        "blurb": "flashcards, diagrams, explainers that teach",
        "skills": ["memento-flashcards", "concept-diagrams", "baoyu-comic"],
    },
    "planner": {
        "blurb": "turns a fog into options, a pick, and a plan of record",
        "skills": ["decision-questionnaire", "one-three-one-rule", "grill-me", "weekly-review-planning", "plan"],
    },
}


def names() -> list:
    return sorted(ROLES)


def blurbs() -> str:
    return "\n".join("{}: {}".format(name, ROLES[name]["blurb"]) for name in names())


def skills_for(role: str) -> list:
    return list(ROLES.get(role, {}).get("skills", []))
