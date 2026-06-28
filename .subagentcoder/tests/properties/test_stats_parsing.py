# Feature: local-coder-workflow-improvements, Property 8: Statistics Line Parsing
"""Property test: For any string containing a substring matching the pattern
'<N> tokens in <T>s (<S> tok/s)' (where N is a non-negative integer, T is a positive decimal,
S is a positive decimal), the stats parser SHALL extract tokens_generated = N and
generation_speed = S. For any string NOT containing this pattern, both fields SHALL be None.

**Validates: Requirements 4.2, 4.3**
"""

import re

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from local_coder.stats_parser import ExecutionStats, parse_stats_line

# The pattern used by the parser
_STATS_PATTERN = re.compile(
    r"(\d+)\s+tokens?\s+in\s+(\d+(?:\.\d+)?)s\s+\((\d+(?:\.\d+)?)\s*tok/s\)"
)


@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=1_000_000),
    t=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
    s=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
    prefix=st.text(
        alphabet=st.characters(blacklist_categories=("Nd",)),  # no digits in prefix
        max_size=50,
    ),
    suffix=st.text(max_size=50),
)
def test_valid_stats_line_extraction(
    n: int, t: float, s: float, prefix: str, suffix: str
) -> None:
    """For any valid stats line with known N, T, S values, parse_stats_line extracts correct fields."""
    # Format T and S as the parser expects (decimal representation)
    t_str = f"{t:.2f}"
    s_str = f"{s:.2f}"

    stats_line = f"{prefix}{n} tokens in {t_str}s ({s_str} tok/s){suffix}"

    result = parse_stats_line(stats_line)

    assert result.tokens_generated == n, (
        f"Expected tokens_generated={n}, got {result.tokens_generated} "
        f"for line: '{stats_line}'"
    )
    assert result.generation_speed == float(s_str), (
        f"Expected generation_speed={float(s_str)}, got {result.generation_speed} "
        f"for line: '{stats_line}'"
    )


@settings(max_examples=100)
@given(random_string=st.text(min_size=0, max_size=500))
def test_no_pattern_returns_none_fields(random_string: str) -> None:
    """For any string NOT containing the stats pattern, both fields SHALL be None."""
    # Skip strings that accidentally match the pattern
    assume(not _STATS_PATTERN.search(random_string))

    result = parse_stats_line(random_string)

    assert result.tokens_generated is None, (
        f"Expected tokens_generated=None for non-matching string, got {result.tokens_generated}"
    )
    assert result.generation_speed is None, (
        f"Expected generation_speed=None for non-matching string, got {result.generation_speed}"
    )
