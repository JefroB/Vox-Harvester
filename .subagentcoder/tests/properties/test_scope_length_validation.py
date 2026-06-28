# Feature: subagent-improvements, Property 17: Scope Length Validation
"""Property test: For any string S provided as a --scope value, the validator
shall accept S when len(S) <= 500 and reject S when len(S) > 500.

**Validates: Requirements 7.1**
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models.task_graph import HintsPayload


@settings(max_examples=100)
@given(scope=st.text(min_size=0, max_size=500))
def test_scope_accepts_strings_within_limit(scope: str) -> None:
    """HintsPayload accepts any scope string with length <= 500."""
    payload = HintsPayload(scope=scope)
    assert payload.scope == scope


@settings(max_examples=100)
@given(scope=st.text(min_size=501, max_size=1000))
def test_scope_rejects_strings_exceeding_limit(scope: str) -> None:
    """HintsPayload rejects any scope string with length > 500."""
    with pytest.raises(ValueError, match="scope must be at most 500 characters"):
        HintsPayload(scope=scope)
