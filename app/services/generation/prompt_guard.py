from __future__ import annotations

import re


_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "override_system",
        re.compile(
            r"\b(override|bypass|disregard)\s+(system|safety|policy)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_leak",
        re.compile(
            r"\b(reveal|print|output|dump)\s+(your\s+)?(system\s+prompt|secrets?|credentials?|api\s*key)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_hijack",
        re.compile(
            r"\byou\s+are\s+now\s+(a|an|in)\s+(unrestricted|admin|developer)\b",
            re.IGNORECASE,
        ),
    ),
)


def detect_prompt_injection(text: str) -> list[str]:
    """Return matched prompt-injection rule names found in untrusted text."""
    matches: list[str] = []
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(name)
    return matches


def sanitize_untrusted_text(text: str) -> str:
    """Neutralize XML-like delimiter tags that could break context framing."""
    return text.replace("</untrusted_evidence>", "[/untrusted_evidence]").replace(
        "<untrusted_evidence>", "[untrusted_evidence]"
    )
