"""Concierge: one sentence in, one thing installed, one undo."""

from __future__ import annotations


def register(ctx) -> None:
    from . import commands

    commands.register(ctx)
