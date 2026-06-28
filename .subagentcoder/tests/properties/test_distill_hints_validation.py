# Feature: skill-distillation, Property 14: Hints type validation graceful degradation
"""Property-based tests for hints type validation graceful degradation.

**Validates: Requirements 5.7**

For any value provided for `hints.distill` that is not a boolean, or
`hints.tokenBudget` that is not an integer, the hints processor SHALL ignore
the malformed key (treating it as absent), emit a warning containing the
expected type and actual value, and process all remaining valid keys normally.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from orchestrator.hints import validate_and_process_hints
from models.task_graph import HintsPayload


# --- Strategies ---

# Non-boolean values for `distill`: strings, integers, lists, None-like
non_boolean_for_distill = st.one_of(
    st.text(min_size=0, max_size=30),
    st.integers(),
    st.lists(st.booleans(), max_size=3),
    st.none(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.just(0),
    st.just(1),
)

# Non-integer values for `tokenBudget`: strings, floats, booleans, lists
non_integer_for_token_budget = st.one_of(
    st.text(min_size=0, max_size=30),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.lists(st.integers(), max_size=3),
    st.none(),
)

# Valid values for other hint keys to mix in
valid_other_keys = st.fixed_dictionaries({}, optional={
    "preferLocalCoder": st.booleans(),
    "complexity": st.sampled_from(["simple", "complex", "prose"]),
    "skipReview": st.booleans(),
    "scope": st.text(min_size=1, max_size=50),
})


# --- Property Tests ---


@settings(max_examples=100)
@given(
    bad_distill=non_boolean_for_distill,
    other_keys=valid_other_keys,
)
def test_non_boolean_distill_is_ignored(bad_distill, other_keys):
    """When distill has a non-boolean value, payload.distill is None.

    The malformed key is treated as absent and a warning is emitted mentioning
    expected type and actual value.
    """
    hints = dict(other_keys)
    hints["distill"] = bad_distill

    payload, warnings = validate_and_process_hints(hints)

    # Assertion 1: distill field is None (treated as absent)
    assert payload is not None
    assert payload.distill is None, (
        f"Expected payload.distill to be None when given non-boolean "
        f"{type(bad_distill).__name__}: {bad_distill!r}, got {payload.distill!r}"
    )

    # Assertion 3: At least one warning mentions expected type and actual value
    distill_warnings = [w for w in warnings if "distill" in w.lower() or "boolean" in w.lower()]
    assert len(distill_warnings) >= 1, (
        f"Expected a warning about malformed 'distill' key, got warnings: {warnings}"
    )
    # The warning should mention the expected type
    warning_text = " ".join(distill_warnings)
    assert "boolean" in warning_text.lower() or "bool" in warning_text.lower(), (
        f"Warning should mention expected type 'boolean', got: {distill_warnings}"
    )


@settings(max_examples=100)
@given(
    bad_budget=non_integer_for_token_budget,
    other_keys=valid_other_keys,
)
def test_non_integer_token_budget_is_ignored(bad_budget, other_keys):
    """When tokenBudget has a non-integer value, payload.token_budget is None.

    The malformed key is treated as absent and a warning is emitted mentioning
    expected type and actual value.
    """
    hints = dict(other_keys)
    hints["tokenBudget"] = bad_budget
    # Even if distill is True, a non-integer budget should still be ignored
    hints["distill"] = True

    payload, warnings = validate_and_process_hints(hints)

    # Assertion 2: token_budget field is None (treated as absent)
    assert payload is not None
    assert payload.token_budget is None, (
        f"Expected payload.token_budget to be None when given non-integer "
        f"{type(bad_budget).__name__}: {bad_budget!r}, got {payload.token_budget!r}"
    )

    # Assertion 3: At least one warning mentions expected type and actual value
    budget_warnings = [w for w in warnings if "tokenbudget" in w.lower() or "integer" in w.lower()]
    assert len(budget_warnings) >= 1, (
        f"Expected a warning about malformed 'tokenBudget' key, got warnings: {warnings}"
    )
    # The warning should mention the expected type
    warning_text = " ".join(budget_warnings)
    assert "integer" in warning_text.lower() or "int" in warning_text.lower(), (
        f"Warning should mention expected type 'integer', got: {budget_warnings}"
    )


@settings(max_examples=100)
@given(
    bad_distill=non_boolean_for_distill,
    other_keys=valid_other_keys,
)
def test_other_valid_keys_processed_when_distill_malformed(bad_distill, other_keys):
    """Other valid keys in the same hints dict are still correctly processed
    when distill has a non-boolean value.
    """
    hints = dict(other_keys)
    hints["distill"] = bad_distill

    payload, warnings = validate_and_process_hints(hints)

    # Assertion 4: All other valid keys are correctly processed
    assert payload is not None

    if "preferLocalCoder" in other_keys:
        assert payload.prefer_local_coder == other_keys["preferLocalCoder"], (
            f"preferLocalCoder should be {other_keys['preferLocalCoder']!r}, "
            f"got {payload.prefer_local_coder!r}"
        )

    if "complexity" in other_keys:
        assert payload.complexity == other_keys["complexity"], (
            f"complexity should be {other_keys['complexity']!r}, "
            f"got {payload.complexity!r}"
        )

    if "skipReview" in other_keys:
        assert payload.skip_review == other_keys["skipReview"], (
            f"skipReview should be {other_keys['skipReview']!r}, "
            f"got {payload.skip_review!r}"
        )

    if "scope" in other_keys:
        assert payload.scope == other_keys["scope"], (
            f"scope should be {other_keys['scope']!r}, "
            f"got {payload.scope!r}"
        )


@settings(max_examples=100)
@given(
    bad_budget=non_integer_for_token_budget,
    other_keys=valid_other_keys,
)
def test_other_valid_keys_processed_when_token_budget_malformed(bad_budget, other_keys):
    """Other valid keys in the same hints dict are still correctly processed
    when tokenBudget has a non-integer value.
    """
    hints = dict(other_keys)
    hints["tokenBudget"] = bad_budget
    hints["distill"] = True  # distill is valid, only tokenBudget is bad

    payload, warnings = validate_and_process_hints(hints)

    # Assertion 4: All other valid keys are correctly processed
    assert payload is not None

    # distill is valid here
    assert payload.distill is True, (
        f"distill should be True (valid), got {payload.distill!r}"
    )

    if "preferLocalCoder" in other_keys:
        assert payload.prefer_local_coder == other_keys["preferLocalCoder"], (
            f"preferLocalCoder should be {other_keys['preferLocalCoder']!r}, "
            f"got {payload.prefer_local_coder!r}"
        )

    if "complexity" in other_keys:
        assert payload.complexity == other_keys["complexity"], (
            f"complexity should be {other_keys['complexity']!r}, "
            f"got {payload.complexity!r}"
        )

    if "skipReview" in other_keys:
        assert payload.skip_review == other_keys["skipReview"], (
            f"skipReview should be {other_keys['skipReview']!r}, "
            f"got {payload.skip_review!r}"
        )

    if "scope" in other_keys:
        assert payload.scope == other_keys["scope"], (
            f"scope should be {other_keys['scope']!r}, "
            f"got {payload.scope!r}"
        )


@settings(max_examples=100)
@given(
    bad_distill=non_boolean_for_distill,
    bad_budget=non_integer_for_token_budget,
    other_keys=valid_other_keys,
)
def test_both_distill_and_token_budget_malformed(bad_distill, bad_budget, other_keys):
    """When both distill and tokenBudget are malformed, both are ignored,
    warnings are emitted for each, and other valid keys still work.
    """
    hints = dict(other_keys)
    hints["distill"] = bad_distill
    hints["tokenBudget"] = bad_budget

    payload, warnings = validate_and_process_hints(hints)

    assert payload is not None

    # Both malformed fields should be None
    assert payload.distill is None, (
        f"distill should be None, got {payload.distill!r}"
    )
    assert payload.token_budget is None, (
        f"token_budget should be None, got {payload.token_budget!r}"
    )

    # Warnings emitted for both malformed keys
    warning_text = " ".join(warnings)
    assert "distill" in warning_text.lower() or "boolean" in warning_text.lower(), (
        f"Expected warning about malformed distill, got: {warnings}"
    )
    assert "tokenbudget" in warning_text.lower() or "integer" in warning_text.lower(), (
        f"Expected warning about malformed tokenBudget, got: {warnings}"
    )

    # Other valid keys still processed correctly
    if "preferLocalCoder" in other_keys:
        assert payload.prefer_local_coder == other_keys["preferLocalCoder"]
    if "complexity" in other_keys:
        assert payload.complexity == other_keys["complexity"]
    if "skipReview" in other_keys:
        assert payload.skip_review == other_keys["skipReview"]
    if "scope" in other_keys:
        assert payload.scope == other_keys["scope"]
