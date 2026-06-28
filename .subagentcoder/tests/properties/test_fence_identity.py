# Feature: subagent-improvements, Property 12: Fence Stripping — Identity for Unfenced Text
"""Property-based tests for fence stripping identity on unfenced text.

**Validates: Requirements 5.4**

For any text that does not contain the triple-backtick fence marker sequence,
the strip function shall return the text unchanged (identity transformation).
"""

import sys
from pathlib import Path

# Make fence_strip importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / ".kiro" / "scripts"))

from hypothesis import given, settings
from hypothesis import strategies as st

from fence_strip import strip_markdown_fences


# --- Strategies ---

# Generate random text that does NOT contain ``` (triple backtick sequence)
unfenced_text = st.text().filter(lambda s: "```" not in s)


# --- Property Tests ---


@settings(max_examples=100)
@given(text=unfenced_text)
def test_unfenced_text_returns_unchanged(text):
    """Text without triple-backtick fences is returned as-is (identity)."""
    result, was_stripped = strip_markdown_fences(text)
    assert result == text
    assert was_stripped is False
