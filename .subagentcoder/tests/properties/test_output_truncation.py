# Feature: subagent-improvements, Property 9: Output Truncation to 200 Lines
"""Property test: For any combined stdout/stderr output from a failed checkpoint,
the reported output shall contain at most 200 lines, and those lines shall be the
last 200 lines of the full output (preserving recency).

**Validates: Requirements 4.3**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestrator.checkpoint import _truncate_output, MAX_OUTPUT_LINES


# Characters that str.splitlines() treats as line boundaries — must be excluded
# from line content to keep line count predictable when joining with "\n".
_LINE_SEPARATORS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"

# Strategy: Generate random output strings with line counts from 1 to 1000
# Each line is a non-empty string without any line-separator characters
lines_strategy = st.lists(
    st.text(
        alphabet=st.characters(blacklist_characters=_LINE_SEPARATORS),
        min_size=1,
        max_size=80,
    ),
    min_size=1,
    max_size=1000,
)


@settings(max_examples=100)
@given(lines=lines_strategy)
def test_truncated_output_has_at_most_200_lines(lines: list[str]) -> None:
    """Result always has at most 200 lines regardless of input size."""
    output = "\n".join(lines)
    result = _truncate_output(output)
    result_lines = result.splitlines()
    assert len(result_lines) <= MAX_OUTPUT_LINES


@settings(max_examples=100)
@given(lines=st.lists(
    st.text(
        alphabet=st.characters(blacklist_characters=_LINE_SEPARATORS),
        min_size=1,
        max_size=80,
    ),
    min_size=MAX_OUTPUT_LINES + 1,
    max_size=1000,
))
def test_truncation_preserves_last_200_lines(lines: list[str]) -> None:
    """When input has > 200 lines, result contains the LAST 200 lines of the input."""
    output = "\n".join(lines)
    result = _truncate_output(output)
    result_lines = result.splitlines()
    expected_lines = lines[-MAX_OUTPUT_LINES:]
    assert result_lines == expected_lines


@settings(max_examples=100)
@given(lines=st.lists(
    st.text(
        alphabet=st.characters(blacklist_characters=_LINE_SEPARATORS),
        min_size=1,
        max_size=80,
    ),
    min_size=1,
    max_size=MAX_OUTPUT_LINES,
))
def test_output_within_limit_returned_unchanged(lines: list[str]) -> None:
    """When input has ≤ 200 lines, result equals the input unchanged."""
    output = "\n".join(lines)
    result = _truncate_output(output)
    assert result == output
