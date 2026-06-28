# Feature: subagent-improvements, Property 15: Symbol Splice Correctness
"""Property-based tests for symbol splice correctness.

**Validates: Requirements 6.6**

For any file containing a symbol at lines [S, E], when the model produces
replacement content for that symbol, the splice operation shall replace only
lines S through E with the new content, leaving all lines outside [S, E]
unchanged.
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# --- Splice function under test ---
# Mirrors the splice logic in local_coder.py

def splice_symbol(file_lines: list[str], start_line: int, end_line: int, replacement_lines: list[str]) -> list[str]:
    """Splice replacement content into file at the symbol's line range.

    Args:
        file_lines: Original file lines (with line endings via splitlines(keepends=True)).
        start_line: 1-based start line of the symbol.
        end_line: 1-based end line of the symbol.
        replacement_lines: New content lines to insert.

    Returns:
        New list of lines with the splice applied.
    """
    start_idx = start_line - 1  # 0-based
    end_idx = end_line  # exclusive
    spliced = file_lines[:start_idx] + replacement_lines + file_lines[end_idx:]
    return spliced


# --- Strategies ---

# Generate a single file line (non-empty, ends with newline)
file_line = st.text(
    alphabet=st.characters(blacklist_characters="\n\r\x00"),
    min_size=1,
    max_size=60,
).map(lambda s: s + "\n")

# Generate replacement lines (1-10 lines, each ending with newline)
replacement_content = st.lists(
    file_line,
    min_size=1,
    max_size=10,
)


@st.composite
def splice_scenario(draw):
    """Generate a valid splice scenario: file lines, start, end, replacement.

    Returns (file_lines, start_line, end_line, replacement_lines) where:
    - file_lines has 5–50 lines
    - start_line and end_line are valid 1-based indices (S <= E <= N)
    - replacement_lines has 1–10 lines
    """
    # Generate file with 5-50 lines
    num_lines = draw(st.integers(min_value=5, max_value=50))
    lines = draw(st.lists(file_line, min_size=num_lines, max_size=num_lines))

    # Pick valid start and end (1-based)
    start_line = draw(st.integers(min_value=1, max_value=num_lines))
    end_line = draw(st.integers(min_value=start_line, max_value=num_lines))

    # Generate replacement content
    replacement = draw(replacement_content)

    return (lines, start_line, end_line, replacement)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=splice_scenario())
def test_lines_before_symbol_unchanged(data):
    """Lines before the symbol (indices 0..S-2) are unchanged after splice."""
    file_lines, start_line, end_line, replacement = data

    spliced = splice_symbol(file_lines, start_line, end_line, replacement)

    # Lines before start_line should be identical
    prefix = file_lines[:start_line - 1]
    assert spliced[:start_line - 1] == prefix


@settings(max_examples=100)
@given(data=splice_scenario())
def test_lines_after_symbol_unchanged(data):
    """Lines after the symbol (indices E..N-1) are unchanged after splice."""
    file_lines, start_line, end_line, replacement = data

    spliced = splice_symbol(file_lines, start_line, end_line, replacement)

    # Lines after end_line should be identical
    suffix = file_lines[end_line:]
    # In the spliced result, the suffix starts after the prefix + replacement
    splice_suffix_start = (start_line - 1) + len(replacement)
    assert spliced[splice_suffix_start:] == suffix


@settings(max_examples=100)
@given(data=splice_scenario())
def test_replacement_content_inserted_at_correct_position(data):
    """The replacement lines appear at position S-1 in the spliced result."""
    file_lines, start_line, end_line, replacement = data

    spliced = splice_symbol(file_lines, start_line, end_line, replacement)

    # The replacement content should be at indices [start_line-1, start_line-1+len(replacement))
    start_idx = start_line - 1
    assert spliced[start_idx:start_idx + len(replacement)] == replacement


@settings(max_examples=100)
@given(data=splice_scenario())
def test_spliced_length_is_correct(data):
    """Spliced file length = original - replaced_lines + replacement_lines."""
    file_lines, start_line, end_line, replacement = data

    spliced = splice_symbol(file_lines, start_line, end_line, replacement)

    original_len = len(file_lines)
    removed_count = end_line - start_line + 1
    expected_len = original_len - removed_count + len(replacement)
    assert len(spliced) == expected_len
