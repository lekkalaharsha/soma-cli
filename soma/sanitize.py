"""Redaction of credential-looking strings — applied to every stored SOMA output.

Security contract (CLAUDE.md): api_key=/secret=/token= assignments, Bearer
tokens, sk-/ghp_ keys, and 40+ char base64 blobs must never appear in any
output. Over-redaction is acceptable; leakage is not.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api_?key|secret|token|password)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    # base64-ish blob: 40+ chars with no path/word context on either side
    re.compile(r"(?<![\w/.+-])[A-Za-z0-9+/]{40,}={0,2}(?![\w/.+-])"),
)


def redact(text: str) -> str:
    """Replace every credential-looking substring with [REDACTED]."""
    for pattern in PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text
