# Feature: subagent-improvements, Property 3: Concurrency Field Validation
"""Property-based tests for WaveConfig concurrency field validation.

**Validates: Requirements 1.5**

For any concurrency metadata value, the validator shall accept "parallel",
"sequential", and integers in [1, 64] inclusive, and shall reject all other
values (strings other than the two keywords, non-integer numbers, integers
outside [1, 64], null, objects, arrays).
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.task_graph import WaveConfig


# --- Strategies ---

valid_concurrency_values = st.one_of(
    st.just("parallel"),
    st.just("sequential"),
    st.integers(min_value=1, max_value=64),
)

invalid_strings = st.text(min_size=1).filter(
    lambda s: s not in ("parallel", "sequential")
)

invalid_ints_low = st.integers(max_value=0)
invalid_ints_high = st.integers(min_value=65)

invalid_concurrency_values = st.one_of(
    # Strings other than the two keywords
    invalid_strings,
    # Integers outside [1, 64]
    invalid_ints_low,
    invalid_ints_high,
    # Floats (non-integer numbers)
    st.floats(allow_nan=False, allow_infinity=False),
    # Booleans (explicitly rejected even though bool is subclass of int)
    st.booleans(),
    # None
    st.none(),
    # Objects (dicts)
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
    # Arrays (lists)
    st.lists(st.integers(), max_size=5),
)


# --- Property Tests ---


@settings(max_examples=100)
@given(value=valid_concurrency_values)
def test_valid_concurrency_values_accepted(value):
    """WaveConfig accepts 'parallel', 'sequential', and integers in [1, 64]."""
    wave = WaveConfig(id="test-wave", concurrency=value)
    assert wave.concurrency == value


@settings(max_examples=100)
@given(value=invalid_concurrency_values)
def test_invalid_concurrency_values_rejected(value):
    """WaveConfig rejects all values outside the valid set."""
    with pytest.raises(ValueError):
        WaveConfig(id="test-wave", concurrency=value)
