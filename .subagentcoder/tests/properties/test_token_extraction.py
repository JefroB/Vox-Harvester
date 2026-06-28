# Feature: local-coder-task-intelligence, Properties 7–8: Token Extraction
"""Property-based tests for token extraction and report formatting.

Tests validate that:
- Property 7: Token extraction returns eval_count or fallback estimate
- Property 8: Token report format is non-empty and well-structured
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st


# --- Helper functions under test ---
# These encapsulate the extraction logic from local_coder.py (task 5.1 fix)


def extract_token_count(result: dict, response_text: str) -> int:
    """Extract token count from Ollama response dict with fallback estimation.

    When eval_count is present and > 0, returns eval_count.
    When eval_count is missing or 0, returns len(response_text) // 4.
    """
    eval_count = result.get("eval_count")
    if eval_count is None or eval_count == 0:
        return len(response_text) // 4
    return eval_count


def format_token_report(count: int, duration_s: float) -> str:
    """Format a token report string: '{count} tokens in {duration}s'."""
    return f"{count} tokens in {duration_s:.1f}s"


# --- Generators ---


@st.composite
def ollama_response_dicts(draw):
    """Generate dicts mimicking Ollama API response shape.

    Produces dicts that may or may not contain eval_count, and when present
    the value may be 0, None, or a positive integer.
    """
    has_eval_count = draw(st.booleans())
    if has_eval_count:
        # eval_count can be None, 0, or a positive integer
        eval_count = draw(
            st.one_of(
                st.none(),
                st.just(0),
                st.integers(min_value=1, max_value=1_000_000),
            )
        )
        result = {"eval_count": eval_count}
    else:
        result = {}

    # Optionally include other fields that exist in real Ollama responses
    if draw(st.booleans()):
        result["total_duration"] = draw(st.integers(min_value=0, max_value=60_000_000_000))
    if draw(st.booleans()):
        result["model"] = draw(st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b-a3b-q4_K_M"]))
    if draw(st.booleans()):
        result["response"] = draw(st.text(min_size=0, max_size=200))

    return result


def response_texts():
    """Generate response text strings of varying lengths."""
    return st.text(min_size=0, max_size=2000)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    result=ollama_response_dicts(),
    response_text=response_texts(),
)
def test_property_7_token_extraction_returns_eval_count_or_fallback(result, response_text):
    """Property 7: Token extraction returns eval_count or fallback estimate.

    **Validates: Requirements 4.1, 4.2**

    For any Ollama response dict, when eval_count is present and > 0, the
    extracted token count SHALL equal eval_count. When eval_count is missing
    or null, the extracted token count SHALL equal len(response_text) // 4.
    """
    extracted = extract_token_count(result, response_text)

    eval_count = result.get("eval_count")
    if eval_count is not None and eval_count > 0:
        # Property: when eval_count present and > 0, use it directly
        assert extracted == eval_count, (
            f"Expected eval_count={eval_count}, got {extracted}"
        )
    else:
        # Property: when eval_count missing, None, or 0, use fallback
        expected_fallback = len(response_text) // 4
        assert extracted == expected_fallback, (
            f"Expected fallback estimate={expected_fallback}, got {extracted}. "
            f"eval_count={eval_count!r}, response_text length={len(response_text)}"
        )


@settings(max_examples=100)
@given(
    count=st.integers(min_value=1, max_value=1_000_000),
    duration_s=st.floats(min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False),
)
def test_property_8_token_report_format_is_well_structured(count, duration_s):
    """Property 8: Token report format is non-empty and well-structured.

    **Validates: Requirements 4.6**

    For any token count > 0 and duration > 0, the formatted token string
    SHALL match the pattern "{count} tokens in {duration}s" and SHALL be
    non-empty.
    """
    report = format_token_report(count, duration_s)

    # Must be non-empty
    assert report, "Token report must be non-empty"

    # Must match the expected pattern: "{count} tokens in {duration}s"
    pattern = r"^\d+ tokens in \d+\.\d+s$"
    assert re.match(pattern, report), (
        f"Report '{report}' does not match pattern '{pattern}'"
    )

    # Verify the count portion is correct
    assert report.startswith(f"{count} tokens in "), (
        f"Report should start with '{count} tokens in ', got: '{report}'"
    )

    # Verify duration portion ends with 's'
    assert report.endswith("s"), f"Report should end with 's', got: '{report}'"
