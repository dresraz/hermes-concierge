"""Words, without a regular expression.

Every routing rule that used a pattern was a guess about phrasing. What is left
here is only mechanics: splitting a sentence into tokens, folding case, dropping
a plural. The model decides meaning; this file never does.
"""

from __future__ import annotations

_SEPARATORS = " \t\n\r,.;:!?()[]{}<>\"'/\\|=+*&^%$#@~`"


def clean(text: str) -> str:
    """Collapse whitespace and strip the edges."""
    return " ".join((text or "").split()).strip()


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


def spaced(text: str) -> str:
    """Punctuation to spaces, for a phrase lookup that must not glue words."""
    out = []
    for char in (text or "").lower():
        out.append(char if (char.isalnum() or char in " -_") else " ")
    return " ".join("".join(out).split())


def bare(word: str) -> str:
    """'pdfs' and 'pdf' are the same word to a person."""
    word = (word or "").lower()
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def slug(text: str) -> str:
    """A profile-safe name: 'Research Bot!' -> 'research-bot'."""
    return "-".join(words(text))


def first_token(text: str) -> str:
    tokens = words(text)
    return tokens[0] if tokens else ""


def digits(text: str) -> str:
    """Every digit in the text, in order."""
    return "".join(char for char in (text or "") if char.isdigit())


def after(text: str, word: str) -> str:
    """What follows the first occurrence of a word, or ''."""
    low = (text or "").lower()
    at = low.find(" " + word.lower() + " ")
    if at < 0:
        return ""
    return clean((text or "")[at + len(word) + 2 :])
