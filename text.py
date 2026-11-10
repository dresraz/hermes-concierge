"""Words, without decisions.

Splitting a sentence into tokens is mechanics. Meaning lives in the model.
This file never decides anything.
"""

from __future__ import annotations


def words(text: str) -> list:
    out: list = []
    token: list = []
    prev_lower = False
    for char in text or "":
        if char.isalnum():
            if char.isupper() and prev_lower and token:
                out.append("".join(token))
                token = []
            token.append(char.lower())
            prev_lower = char.islower()
        elif token:
            out.append("".join(token))
            token = []
            prev_lower = False
        else:
            prev_lower = False
    if token:
        out.append("".join(token))
    return out


def slug(text: str) -> str:
    return "-".join(words(text))
