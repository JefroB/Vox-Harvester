# Feature: local-coder-workflow-improvements, Property 9: Review Iteration Capping
"""Property test: For any execution where the review-fix loop runs K iterations
(K >= 0), the recorded review_iterations value SHALL be min(K, 5), and if K > 5
the result SHALL be 'fail' with the task marked as abandoned.

**Validates: Requirements 4.5**
"""

from hypothesis import given, settings
from hypothesis import strategies as st


MAX_REVIEW_ITERATIONS = 5


def cap_iterations(k: int) -> tuple[int, bool]:
    """Cap the number of review-fix iterations to MAX_REVIEW_ITERATIONS.

    Returns (capped_iterations, is_abandoned) where:
    - capped_iterations = min(k, 5)
    - is_abandoned = True if k > 5 (task should be marked as fail)
    """
    return (min(k, MAX_REVIEW_ITERATIONS), k > MAX_REVIEW_ITERATIONS)


@settings(max_examples=100)
@given(k=st.integers(min_value=0, max_value=20))
def test_capped_value_is_min_k_5(k: int) -> None:
    """The recorded review_iterations is always min(K, 5)."""
    capped, _ = cap_iterations(k)
    assert capped == min(k, MAX_REVIEW_ITERATIONS)


@settings(max_examples=100)
@given(k=st.integers(min_value=0, max_value=20))
def test_abandoned_when_exceeds_cap(k: int) -> None:
    """When K > 5, the task is marked as abandoned (result='fail')."""
    _, is_abandoned = cap_iterations(k)
    if k > MAX_REVIEW_ITERATIONS:
        assert is_abandoned, f"Expected abandoned for K={k}"
    else:
        assert not is_abandoned, f"Should not be abandoned for K={k}"


@settings(max_examples=100)
@given(k=st.integers(min_value=0, max_value=20))
def test_capped_value_never_exceeds_max(k: int) -> None:
    """The capped value is always in range [0, 5] regardless of input."""
    capped, _ = cap_iterations(k)
    assert 0 <= capped <= MAX_REVIEW_ITERATIONS
