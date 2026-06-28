# Feature: subagent-improvements, Property 10: Fence Stripping — Nested Fence Correctness
"""Property-based tests for nested fence handling in strip_markdown_fences.

**Validates: Requirements 5.1**

For any text containing nested markdown fences (fences within fences),
the stripper shall treat only outermost fence pairs as boundaries,
preserving inner ``` lines as literal content in the extracted output.
"""

import sys
from pathlib import Path

# Make fence_strip importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from fence_strip import strip_markdown_fences


# --- Strategies ---

# Generate non-fence content lines (no triple backticks)
non_fence_line = st.text(
    alphabet=st.characters(blacklist_characters="`\n\r"),
    min_size=0,
    max_size=80,
).filter(lambda s: "```" not in s)

# Generate a language tag (optional, for opening fences)
language_tag = st.one_of(
    st.just(""),
    st.sampled_from(["python", "js", "typescript", "rust", "c", "java", "go"]),
)

# Generate inner fence backtick count (fewer than outer)
# Outer will always be >= 4 backticks, inner will be exactly 3
inner_backtick_count = st.just(3)

# Outer backtick count: 4 to 8 (always more than inner's 3)
outer_backtick_count = st.integers(min_value=4, max_value=8)


@st.composite
def nested_fence_text(draw):
    """Generate text with an outer fence wrapping content that contains inner fences.

    Structure:
        ````[lang]       <- outer open (4+ backticks)
        <content line>
        ```             <- inner fence (3 backticks, treated as content)
        <content line>
        ```             <- inner fence (3 backticks, treated as content)
        <content line>
        ````            <- outer close (matching outer backticks)
    """
    outer_ticks = draw(outer_backtick_count)
    outer_marker = "`" * outer_ticks
    lang = draw(language_tag)

    # Generate some content lines before inner fence
    pre_lines = draw(st.lists(non_fence_line, min_size=0, max_size=5))

    # Generate inner fence content (at least one inner fence pair)
    inner_tick_count = draw(inner_backtick_count)
    inner_marker = "`" * inner_tick_count
    inner_lang = draw(language_tag)

    # Content inside the inner fence
    inner_content_lines = draw(st.lists(non_fence_line, min_size=1, max_size=4))

    # Generate some content lines after inner fence
    post_lines = draw(st.lists(non_fence_line, min_size=0, max_size=5))

    # Build the full text with nested fences
    lines = []
    lines.append(f"{outer_marker}{lang}")  # outer open
    lines.extend(pre_lines)
    lines.append(f"{inner_marker}{inner_lang}")  # inner open (content)
    lines.extend(inner_content_lines)
    lines.append(inner_marker)  # inner close (content)
    lines.extend(post_lines)
    lines.append(outer_marker)  # outer close

    text = "\n".join(lines)

    # Build the expected extracted content (everything between outer fences)
    expected_lines = []
    expected_lines.extend(pre_lines)
    expected_lines.append(f"{inner_marker}{inner_lang}")  # inner open preserved
    expected_lines.extend(inner_content_lines)
    expected_lines.append(inner_marker)  # inner close preserved
    expected_lines.extend(post_lines)

    expected = "\n".join(expected_lines)

    return text, expected, inner_marker


@st.composite
def nested_fence_text_multiple_inner(draw):
    """Generate text with outer fence wrapping multiple inner fence blocks.

    Tests that multiple inner fence markers are all preserved as content.
    """
    outer_ticks = draw(outer_backtick_count)
    outer_marker = "`" * outer_ticks

    lang = draw(language_tag)

    # Number of inner fence pairs
    num_inner_blocks = draw(st.integers(min_value=2, max_value=4))

    content_lines = []
    for i in range(num_inner_blocks):
        # Add some regular content before each inner block
        pre = draw(st.lists(non_fence_line, min_size=0, max_size=3))
        content_lines.extend(pre)

        # Inner fence pair (3 backticks)
        inner_lang = draw(language_tag)
        content_lines.append(f"```{inner_lang}")
        inner_content = draw(st.lists(non_fence_line, min_size=1, max_size=3))
        content_lines.extend(inner_content)
        content_lines.append("```")

    # Optional trailing content
    trailing = draw(st.lists(non_fence_line, min_size=0, max_size=3))
    content_lines.extend(trailing)

    # Build full text
    lines = [f"{outer_marker}{lang}"] + content_lines + [outer_marker]
    text = "\n".join(lines)
    expected = "\n".join(content_lines)

    return text, expected


# --- Property Tests ---


@settings(max_examples=100)
@given(data=nested_fence_text())
def test_inner_fence_lines_preserved_in_output(data):
    """Inner ``` lines appear in the extracted output as literal content.

    When outer fences have more backticks than inner fences, the inner
    fence markers are treated as content and preserved in the output.
    """
    text, expected, inner_marker = data

    result, was_stripped = strip_markdown_fences(text)

    # The inner fence marker must appear in the result
    assert inner_marker in result, (
        f"Inner fence marker '{inner_marker}' should be preserved as content"
    )

    # The output should match the expected content between outer fences
    assert result == expected


@settings(max_examples=100)
@given(data=nested_fence_text())
def test_nested_fences_trigger_was_stripped(data):
    """Text with nested fences should report was_stripped=True.

    The outermost fences are still stripped, so was_stripped must be True.
    """
    text, expected, inner_marker = data

    result, was_stripped = strip_markdown_fences(text)

    assert was_stripped is True


@settings(max_examples=100)
@given(data=nested_fence_text_multiple_inner())
def test_multiple_inner_fence_pairs_preserved(data):
    """Multiple inner fence pairs are all preserved as literal content.

    When outer fences wrap content containing several inner fence blocks,
    all inner ``` lines must appear in the output.
    """
    text, expected = data

    result, was_stripped = strip_markdown_fences(text)

    assert was_stripped is True
    assert result == expected
