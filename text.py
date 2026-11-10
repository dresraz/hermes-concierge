"""Words, without a regular expression.

Every routing rule that used a pattern was a guess about phrasing. What is left
here is only mechanics: splitting a sentence into tokens, folding case, dropping
a plural. The model decides meaning; this file never does.
"""

from __future__ import annotations


def words(text: str) -> list:
    """Lower-case alphanumeric tokens: 'read PDFs!' -> ['read', 'pdfs']."""
    out = []
    token = []
    for char in (text or "").lower():
        if char.isalnum():
            token.append(char)
        elif token:
            out.append("".join(token))
            token = []
    if token:
        out.append("".join(token))
    return out


def slug(text: str) -> str:
    """A profile-safe name: 'Research Bot!' -> 'research-bot'."""
    return "-".join(words(text))
