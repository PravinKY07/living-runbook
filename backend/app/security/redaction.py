"""Redact secrets and selected PII from untrusted repository text."""

from __future__ import annotations

import re

REDACTED_SECRET = "[REDACTED_SECRET]"
REDACTED_TOKEN = "[REDACTED_TOKEN]"
REDACTED_PRIVATE_KEY = "[REDACTED_PRIVATE_KEY]"
REDACTED_CREDENTIALS = "[REDACTED_CREDENTIALS]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
            re.IGNORECASE | re.DOTALL,
        ),
        REDACTED_PRIVATE_KEY,
    ),
    (
        re.compile(
            r"\b(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|secret|password|passwd|pwd)"
            r"\s*([:=])\s*(['\"]?)([^\s'\",;]+)\3",
            re.IGNORECASE,
        ),
        rf"\1\2\3{REDACTED_SECRET}\3",
    ),
    (
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
        f"Bearer {REDACTED_TOKEN}",
    ),
    (
        re.compile(r"\b(?:sk|pk|ghp|gho|ghu|ghs|ghr|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"),
        REDACTED_TOKEN,
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        REDACTED_TOKEN,
    ),
    (
        # A JSON Web Token is a bearer credential. Without this, a token stored
        # under a variable name outside the keyword list survived redaction.
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        REDACTED_TOKEN,
    ),
    (
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE),
        rf"{REDACTED_CREDENTIALS}@",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        REDACTED_EMAIL,
    ),
)


def redact_text(text: str) -> str:
    """Return text with common secret and PII patterns replaced."""
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def contains_secret_like_value(text: str) -> bool:
    """Return whether text still contains a common secret pattern."""
    return redact_text(text) != text
