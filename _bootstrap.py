"""Load the code that is on disk now, not the code this chat started with.

A chat can live for days. Its slash worker imports this package once, when the
chat is created, and would otherwise keep that copy for the life of the chat --
so a fix shipped this afternoon stayed invisible in a conversation opened this
morning, and looked exactly like a bug.

The command and the hook are therefore thin closures into here. Each call stats
the package directory; when the files changed, the old modules are dropped and
the new ones are imported. One `scandir` per command is cheaper than being wrong
about which build is answering.
"""

from __future__ import annotations

import pathlib
import sys

_PACKAGE = "concierge"
_HERE = pathlib.Path(__file__).resolve().parent
_fingerprint: tuple = ()
_ctx = None


def _stamp() -> tuple:
    newest = 0.0
    total = 0
    try:
        for path in _HERE.glob("*.py"):
            stat = path.stat()
            newest = max(newest, stat.st_mtime)
            total += stat.st_size
    except OSError:
        return ()
    return (round(newest, 4), total)


def _current():
    """The live `commands` module, re-imported if the package changed on disk."""
    global _fingerprint

    stamp = _stamp()
    if _fingerprint and stamp != _fingerprint:
        for name in [n for n in sys.modules if n == _PACKAGE or n.startswith(_PACKAGE + ".")]:
            del sys.modules[name]
    _fingerprint = stamp
    module = __import__(_PACKAGE + ".commands", fromlist=["commands"])
    if _ctx is not None:
        module.bind(_ctx)
    return module


def handle(text, **kwargs):
    return _current().handle_concierge(text, **kwargs)


def on_admission(*args, **kwargs):
    module = __import__(_PACKAGE + ".reply", fromlist=["reply"])
    return module.on_admission(*args, **kwargs)


def register(ctx) -> None:
    """Wire /concierge through here, so every call resolves the current code."""
    global _ctx

    _ctx = ctx
    module = _current()
    from . import reply

    ctx.register_command(
        "concierge",
        handler=handle,
        description="Bots, plugins and skills in one sentence: install, create, improve, list, fire, reset, undo.",
        args_hint="<sentence> | create | improve | bots | fire | reset | undo | help",
    )
    ctx.register_hook(reply.HOOK, on_admission)
