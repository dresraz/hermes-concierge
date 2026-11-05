"""Test harness: load plugin modules without installing the plugin.

Hermes loads a directory plugin as a synthetic package whose ``__path__`` is the
plugin root. This rebuilds that shape so tests can ``from . import match`` the
same way the runtime does, with no import shims in production code.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = "concierge_under_test"


def package() -> types.ModuleType:
    mod = sys.modules.get(PACKAGE)
    if mod is None:
        mod = types.ModuleType(PACKAGE)
        mod.__path__ = [str(ROOT)]
        sys.modules[PACKAGE] = mod
    return mod


def load(name: str):
    package()
    return importlib.import_module(f"{PACKAGE}.{name}")
