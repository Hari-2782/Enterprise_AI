from __future__ import annotations

import re


_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "phone",
        re.compile(
            r"(?<!\w)(?:"
            r"\+\d{1,3}[-.\s]?(?:\(?\d{1,4}\)?[-.\s]?){2,4}\d{2,4}"
            r"|"
            r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}"
            r")\b"
        ),
        "[REDACTED_PHONE]",
    ),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
        "[REDACTED_CARD]",
    ),
)


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Mask common PII patterns in text before external LLM transmission."""
    masked = text
    detected: list[str] = []
    for label, pattern, replacement in _PII_PATTERNS:
        if pattern.search(masked):
            detected.append(label)
            masked = pattern.sub(replacement, masked)
    return masked, detected
