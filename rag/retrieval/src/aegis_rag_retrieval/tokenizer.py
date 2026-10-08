from __future__ import annotations

import re

TECHNICAL_TOKEN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", re.IGNORECASE)
SEPARATOR = re.compile(r"[-_.]")


def tokenize(text: str) -> list[str]:
    """Tokenize operational text while retaining useful compound identifiers."""
    tokens: list[str] = []
    for match in TECHNICAL_TOKEN.finditer(text.casefold()):
        token = match.group(0)
        tokens.append(token)
        if SEPARATOR.search(token):
            tokens.extend(part for part in SEPARATOR.split(token) if part)
    return tokens
