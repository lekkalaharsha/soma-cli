"""Tests for soma/sanitize.py — every credential pattern from the security contract."""
from __future__ import annotations

import pytest

from soma.sanitize import redact

# (leaking text, secret payload that must vanish)
LEAKS = [
    ("api_key=AKIA1234567890EXAMPLE", "AKIA1234567890EXAMPLE"),
    ("API_KEY = supersecretvalue", "supersecretvalue"),
    ("secret=hunter2hunter2", "hunter2hunter2"),
    ("token=ghx123abcsecret", "ghx123abcsecret"),
    ("password: opensesame99", "opensesame99"),
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9"),
    ("key sk-" + "a1B2" * 12 + " found", "sk-" + "a1B2" * 12),
    ("ghp_" + "x" * 36, "ghp_" + "x" * 36),
    ("blob " + "A" * 44 + " end", "A" * 44),
]


@pytest.mark.parametrize("text,payload", LEAKS)
def test_credential_patterns_redacted(text: str, payload: str) -> None:
    out = redact(text)
    assert payload not in out
    assert "[REDACTED]" in out


def test_clean_text_untouched() -> None:
    text = "fix: tokenizer handles api keys section in docs/secrets_policy.md"
    assert redact(text) == text


def test_normal_paths_and_messages_survive() -> None:
    text = "- src/radar_pipeline/processing/parameter_sweep_stage_3.py (2h ago)"
    assert redact(text) == text
