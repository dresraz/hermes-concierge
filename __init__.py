"""concierge plugin entrypoint.

Registers one slash command and one hook, and nothing else. Every capability
lives in a sibling module so one concern owns one file:

  commands.py  the surface behind /concierge, the one-yes protocol, undo
  match.py     deterministic ranking of a free-text ask against the live catalog
  card.py      the one card, and the receipt that reads the disk back
  lifecycle.py the bots Concierge made: list, remove, reset
  bots.py      hire: a sentence into a new bot
  training.py  train: a sentence into a standing behaviour on an existing bot
  seams.py     the only place that calls into core
  effects.py   the writes core never performs (SOUL, skills, cron)
  undo.py      reversal of those writes
"""

from __future__ import annotations


def register(ctx) -> None:
    """Wire ``/concierge`` into Hermes. It is the only command to learn."""

    from . import commands

    commands.register(ctx)
