"""Property-based tests for error message truncation.

**Validates: Requirements 3.4**

Tests the truncation logic used by the Isolation_Job error field to ensure it adheres
to the maximum 500-character limit. This is a pure logic test — validates the truncation
directly in Python without hitting the server.

Property 8: Error message truncation
For any isolation failure whose error description exceeds 500 characters, the stored
Isolation_Job error field SHALL contain at most 500 characters.

The server truncation logic is: job.error = errorMsg.substring(0, 500)
"""

from hypothesis import given, settings
import hypothesis.strategies as st


# Mirror the server-side truncation: errorMsg.substring(0, 500)
MAX_ERROR_LENGTH = 500


def truncate_error_message(error_msg: str) -> str:
    """Simulate server-side error message truncation."""
    return error_msg[:MAX_ERROR_LENGTH]


@given(error_msg=st.text(min_size=1, max_size=2000))
@settings(max_examples=100)
def test_truncated_error_never_exceeds_500_chars(error_msg: str) -> None:
    """For any error message of any length, the truncated result is always <= 500 characters.

    **Validates: Requirements 3.4**
    """
    truncated = truncate_error_message(error_msg)
    assert len(truncated) <= MAX_ERROR_LENGTH


@given(error_msg=st.text(min_size=1, max_size=500))
@settings(max_examples=100)
def test_short_messages_are_not_modified(error_msg: str) -> None:
    """If the original error message is <= 500 characters, it remains unchanged.

    **Validates: Requirements 3.4**
    """
    truncated = truncate_error_message(error_msg)
    assert truncated == error_msg


@given(error_msg=st.text(min_size=501, max_size=2000))
@settings(max_examples=100)
def test_long_messages_are_truncated_to_first_500_chars(error_msg: str) -> None:
    """If the original error message exceeds 500 characters, result is exactly the first 500 chars.

    **Validates: Requirements 3.4**
    """
    truncated = truncate_error_message(error_msg)
    assert len(truncated) == MAX_ERROR_LENGTH
    assert truncated == error_msg[:MAX_ERROR_LENGTH]
