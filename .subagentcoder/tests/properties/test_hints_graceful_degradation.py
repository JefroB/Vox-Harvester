# Feature: subagent-improvements, Property 6: Hints Validation with Graceful Degradation
"""Property-based tests for hints validation with graceful degradation.

**Validates: Requirements 3.9**

For any hints object containing a mix of valid and invalid entries (unrecognized
keys or type-mismatched values), all valid entries shall be processed correctly
and all invalid entries shall be ignored with a warning, such that the presence
of invalid entries never affects the processing of valid ones.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from orchestrator.hints import validate_and_process_hints
from models.task_graph import VALID_COMPLEXITY_VALUES, MAX_CONTEXT_FILES


# --- Strategies ---

# Valid hint entries: each is a (key, value) pair that conforms to the schema.
valid_prefer_local_coder = st.tuples(st.just("preferLocalCoder"), st.booleans())
valid_complexity = st.tuples(
    st.just("complexity"),
    st.sampled_from(list(VALID_COMPLEXITY_VALUES)),
)
valid_context_files = st.tuples(
    st.just("contextFiles"),
    st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=MAX_CONTEXT_FILES),
)
valid_skip_review = st.tuples(st.just("skipReview"), st.booleans())
valid_scope = st.tuples(
    st.just("scope"),
    st.text(min_size=0, max_size=100),  # Well within 500 char limit
)
valid_distill = st.tuples(st.just("distill"), st.booleans())
valid_token_budget = st.tuples(
    st.just("tokenBudget"),
    st.integers(min_value=500, max_value=16000),
)

valid_entries = st.one_of(
    valid_prefer_local_coder,
    valid_complexity,
    valid_context_files,
    valid_skip_review,
    valid_scope,
    valid_distill,
    valid_token_budget,
)

# Invalid entries: unrecognized keys (random strings not in the schema)
KNOWN_KEYS = {"preferLocalCoder", "complexity", "contextFiles", "skipReview", "scope", "distill", "tokenBudget"}

unrecognized_keys = st.tuples(
    st.text(min_size=1, max_size=30).filter(lambda s: s not in KNOWN_KEYS),
    # Value can be anything — the key is what makes it invalid
    st.one_of(st.booleans(), st.integers(), st.text(max_size=20), st.none()),
)

# Invalid entries: valid keys with wrong types
wrong_type_prefer_local = st.tuples(
    st.just("preferLocalCoder"),
    st.one_of(st.text(min_size=1, max_size=10), st.integers(), st.none()),
)
wrong_type_complexity = st.tuples(
    st.just("complexity"),
    st.one_of(
        st.booleans(),
        st.integers(),
        st.none(),
        # Strings not in the valid set
        st.text(min_size=1, max_size=20).filter(
            lambda s: s not in VALID_COMPLEXITY_VALUES
        ),
    ),
)
wrong_type_context_files = st.tuples(
    st.just("contextFiles"),
    # Not a list
    st.one_of(st.text(min_size=1, max_size=20), st.integers(), st.booleans(), st.none()),
)
wrong_type_skip_review = st.tuples(
    st.just("skipReview"),
    st.one_of(st.text(min_size=1, max_size=10), st.integers(), st.none()),
)
wrong_type_scope = st.tuples(
    st.just("scope"),
    st.one_of(st.booleans(), st.integers(), st.none(), st.lists(st.text(max_size=5), max_size=3)),
)
wrong_type_distill = st.tuples(
    st.just("distill"),
    st.one_of(st.text(min_size=1, max_size=10), st.integers(), st.none()),
)
wrong_type_token_budget = st.tuples(
    st.just("tokenBudget"),
    st.one_of(st.text(min_size=1, max_size=10), st.booleans(), st.none(), st.lists(st.integers(), max_size=3)),
)

invalid_type_entries = st.one_of(
    wrong_type_prefer_local,
    wrong_type_complexity,
    wrong_type_context_files,
    wrong_type_skip_review,
    wrong_type_scope,
    wrong_type_distill,
    wrong_type_token_budget,
)

invalid_entries = st.one_of(unrecognized_keys, invalid_type_entries)


# --- Helper to build a hints dict from entry lists ---

# Map JSON key → dataclass field name for assertions
KEY_TO_FIELD = {
    "preferLocalCoder": "prefer_local_coder",
    "complexity": "complexity",
    "contextFiles": "context_files",
    "skipReview": "skip_review",
    "scope": "scope",
    "distill": "distill",
    "tokenBudget": "token_budget",
}


# --- Property Tests ---


@settings(max_examples=100)
@given(
    valid=st.lists(valid_entries, min_size=1, max_size=5, unique_by=lambda x: x[0]),
    invalid=st.lists(invalid_entries, min_size=1, max_size=5, unique_by=lambda x: x[0]),
)
def test_valid_entries_processed_correctly_despite_invalid_entries(valid, invalid):
    """Valid entries are processed correctly regardless of invalid entries present.

    Builds a hints dict with a mix of valid and invalid entries. Verifies that
    all valid entries appear in the resulting HintsPayload with correct values,
    and that invalid entries produce warnings without affecting valid processing.
    """
    # Ensure no key collisions between valid and invalid entry lists
    valid_keys = {k for k, _ in valid}
    invalid_keys = {k for k, _ in invalid}
    assume(valid_keys.isdisjoint(invalid_keys))

    # Build a single hints dict with both valid and invalid entries
    hints_dict = {}
    for key, value in valid:
        hints_dict[key] = value
    for key, value in invalid:
        hints_dict[key] = value

    # Process
    payload, warnings = validate_and_process_hints(hints_dict)

    # Valid entries must be in the payload with correct values
    assert payload is not None
    valid_dict = {k: v for k, v in valid}
    for key, value in valid:
        field_name = KEY_TO_FIELD[key]
        # tokenBudget is subject to post-validation: nulled if distill is not True
        if key == "tokenBudget" and valid_dict.get("distill") is not True:
            assert getattr(payload, field_name) is None, (
                f"tokenBudget should be None without distill: true, "
                f"got {getattr(payload, field_name)!r}"
            )
        else:
            assert getattr(payload, field_name) == value, (
                f"Valid entry '{key}' should be {value!r}, "
                f"got {getattr(payload, field_name)!r}"
            )

    # Invalid entries must produce at least one warning each
    assert len(warnings) >= len(invalid), (
        f"Expected at least {len(invalid)} warnings for invalid entries, "
        f"got {len(warnings)}"
    )


@settings(max_examples=100)
@given(
    valid=st.lists(valid_entries, min_size=1, max_size=5, unique_by=lambda x: x[0]),
    invalid=st.lists(invalid_entries, min_size=0, max_size=5, unique_by=lambda x: x[0]),
)
def test_invalid_entries_do_not_affect_valid_processing(valid, invalid):
    """The presence of invalid entries never changes the outcome for valid entries.

    Processes valid entries alone, then processes them mixed with invalid entries.
    The resulting payload fields for valid entries must be identical in both cases.
    """
    valid_keys = {k for k, _ in valid}
    invalid_keys = {k for k, _ in invalid}
    assume(valid_keys.isdisjoint(invalid_keys))

    # Process valid entries only
    valid_only_dict = {k: v for k, v in valid}
    payload_clean, warnings_clean = validate_and_process_hints(valid_only_dict)

    # Process valid + invalid entries mixed
    mixed_dict = dict(valid_only_dict)
    for key, value in invalid:
        mixed_dict[key] = value
    payload_mixed, warnings_mixed = validate_and_process_hints(mixed_dict)

    # Both payloads must have the same valid fields
    assert payload_clean is not None
    assert payload_mixed is not None
    for key, _ in valid:
        field_name = KEY_TO_FIELD[key]
        assert getattr(payload_clean, field_name) == getattr(payload_mixed, field_name), (
            f"Field '{field_name}' differs when invalid entries are present: "
            f"clean={getattr(payload_clean, field_name)!r}, "
            f"mixed={getattr(payload_mixed, field_name)!r}"
        )


@settings(max_examples=100)
@given(invalid=st.lists(invalid_entries, min_size=1, max_size=5, unique_by=lambda x: x[0]))
def test_all_invalid_entries_produce_warnings(invalid):
    """Every invalid entry (unrecognized key or wrong type) produces a warning."""
    hints_dict = {k: v for k, v in invalid}

    payload, warnings = validate_and_process_hints(hints_dict)

    # Should still return a payload (possibly with all-None fields)
    assert payload is not None

    # Each invalid entry should generate exactly one warning
    assert len(warnings) == len(invalid), (
        f"Expected exactly {len(invalid)} warnings, got {len(warnings)}: {warnings}"
    )

    # Each warning should contain [WARN]
    for w in warnings:
        assert "[WARN]" in w
