# Feature: subagent-improvements, Property 11: Fence Stripping — Extraction Round Trip
"""Property-based tests for fence stripping extraction round trip.

**Validates: Requirements 5.2, 5.3**

For any sequence of N ≥ 1 code blocks (arbitrary string content not containing
the fence marker sequence), wrapping each in markdown fences with optional
language tags and interleaving arbitrary non-fence text, the strip function shall
extract exactly those N blocks' contents joined by a single newline separator.
"""

import sys
from pathlib import Path

# Make fence_strip importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from fence_strip import strip_markdown_fences


# --- Strategies ---

# Code block content: arbitrary text not containing ``` and not empty/whitespace-only
block_content_strategy = st.text().filter(lambda s: "```" not in s and s.strip())

# Language tags: empty or a known language identifier
language_tag_strategy = st.one_of(
    st.just(""),
    st.sampled_from(["python", "js", "rust", ""]),
)

# Lists of code blocks (1 to 5)
blocks_strategy = st.lists(
    block_content_strategy,
    min_size=1,
    max_size=5,
)

# Interleaving non-fence text (text between code blocks)
interleave_text_strategy = st.text().filter(lambda s: "```" not in s)


# --- Helpers ---

def wrap_blocks_with_fences(blocks: list[str], lang_tags: list[str], interleaves: list[str]) -> str:
    """Wrap each block in markdown fences with optional language tags,
    interleaving arbitrary non-fence text between blocks."""
    parts = []
    for i, (block, lang) in enumerate(zip(blocks, lang_tags)):
        if i < len(interleaves):
            parts.append(interleaves[i])
        parts.append(f"```{lang}")
        parts.append(block)
        parts.append("```")
    # Add trailing interleave if available
    if len(interleaves) > len(blocks) - 1:
        for extra in interleaves[len(blocks):]:
            parts.append(extra)
    return "\n".join(parts)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    blocks=blocks_strategy,
    lang_tags=st.lists(language_tag_strategy, min_size=5, max_size=5),
    interleaves=st.lists(interleave_text_strategy, min_size=0, max_size=6),
)
def test_extraction_round_trip(blocks, lang_tags, interleaves):
    """Wrapping N code blocks in fences with interleaved text, strip_markdown_fences
    extracts exactly those N blocks' contents joined by a single newline separator."""
    # Trim lang_tags to match blocks length
    lang_tags = lang_tags[: len(blocks)]

    # Build the fenced markdown document
    document = wrap_blocks_with_fences(blocks, lang_tags, interleaves)

    # Call the strip function
    result, was_stripped = strip_markdown_fences(document)

    # Expected: all block contents joined by single newline
    expected = "\n".join(blocks)

    assert was_stripped is True, "was_stripped should be True when fences are present"
    assert result == expected, (
        f"Expected extracted content to match original blocks joined by newline.\n"
        f"Got: {result!r}\n"
        f"Expected: {expected!r}"
    )
