# Feature: local-coder-reliability, Properties 4 & 5: Garbage Detection
"""Property tests for garbage_detector module.

Property 4: Garbage Classification Threshold (Requirements 6.1)
Property 5: Diagnostic Message Formatting (Requirements 6.3, 6.4)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.garbage_detector import (
    GarbageCheckResult,
    check_garbage,
    format_escalation_warning,
    format_garbage_log,
)


# Validates: Requirements 6.1
@settings(max_examples=100)
@given(output=st.text())
def test_garbage_classification_threshold(output: str) -> None:
    """Feature: local-coder-reliability, Property 4: Garbage Classification Threshold"""
    result = check_garbage(output)
    assert result.is_garbage == (len(output) // 4 < 50), f"Failed for output length {len(output)}"
    assert result.token_count == len(output) // 4, f"Token count mismatch for output length {len(output)}"


@settings(max_examples=100)
@given(
    token_count=st.integers(min_value=0),
    attempt=st.integers(min_value=1),
)
def test_format_garbage_log_exact_format(token_count: int, attempt: int) -> None:
    """format_garbage_log produces exactly '[GARBAGE] {token_count} tokens (attempt {attempt})'."""
    result = GarbageCheckResult(is_garbage=True, token_count=token_count, attempt=attempt)
    expected = f"[GARBAGE] {token_count} tokens (attempt {attempt})"
    actual = format_garbage_log(result)
    assert actual == expected, (
        f"format_garbage_log mismatch.\n"
        f"  Expected: '{expected}'\n"
        f"  Got:      '{actual}'"
    )


@settings(max_examples=100)
@given(
    task_id=st.text(min_size=1, max_size=100),
)
def test_format_escalation_warning_exact_format(task_id: str) -> None:
    """format_escalation_warning produces exactly
    '[RETRY FAIL] Task {task_id} produced garbage on retry — escalating to cloud'."""
    expected = f"[RETRY FAIL] Task {task_id} produced garbage on retry \u2014 escalating to cloud"
    actual = format_escalation_warning(task_id)
    assert actual == expected, (
        f"format_escalation_warning mismatch.\n"
        f"  Expected: '{expected}'\n"
        f"  Got:      '{actual}'"
    )
