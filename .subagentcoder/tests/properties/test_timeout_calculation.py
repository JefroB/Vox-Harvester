# Feature: subagent-improvements, Property 16: Timeout Calculation
"""Property test: For any non-negative integer token count T, the calculated
timeout shall equal min(60 + (T // 100) * 3, 600), and the result shall always
be in the range [60, 600].

**Validates: Requirements 6.8**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.patch_mode import calculate_timeout


@settings(max_examples=100)
@given(t=st.integers(min_value=0, max_value=100000))
def test_timeout_formula_correctness(t: int) -> None:
    """calculate_timeout(t) equals min(60 + (t // 100) * 3, 600)."""
    expected = min(60 + (t // 100) * 3, 600)
    assert calculate_timeout(t) == expected


@settings(max_examples=100)
@given(t=st.integers(min_value=0, max_value=100000))
def test_timeout_range_invariant(t: int) -> None:
    """calculate_timeout(t) is always in the range [60, 600]."""
    result = calculate_timeout(t)
    assert 60 <= result <= 600
