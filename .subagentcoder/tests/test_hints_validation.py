"""Smoke tests for validate_and_process_hints()."""

from models.task_graph import HintsPayload
from orchestrator.hints import validate_and_process_hints


def test_all_valid_hints_processed():
    """All recognized keys with correct types produce a fully populated payload."""
    raw = {
        "preferLocalCoder": True,
        "complexity": "simple",
        "contextFiles": ["src/models.py", "src/schema.py"],
        "skipReview": False,
        "scope": "validate_email, lines 10-50",
    }

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.prefer_local_coder is True
    assert payload.complexity == "simple"
    assert payload.context_files == ["src/models.py", "src/schema.py"]
    assert payload.skip_review is False
    assert payload.scope == "validate_email, lines 10-50"
    assert warnings == []


def test_unrecognized_keys_ignored_with_warning():
    """Unrecognized keys produce a warning and are skipped."""
    raw = {
        "preferLocalCoder": True,
        "unknownKey": "some_value",
        "anotherBadKey": 42,
    }

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.prefer_local_coder is True
    assert len(warnings) == 2
    assert "unrecognized key 'unknownKey'" in warnings[0]
    assert "unrecognized key 'anotherBadKey'" in warnings[1]


def test_type_mismatch_ignored_with_warning():
    """Type-mismatched values produce a warning and are skipped."""
    raw = {
        "preferLocalCoder": "yes",  # should be bool
        "complexity": 123,  # should be string enum
        "skipReview": True,  # valid
    }

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.prefer_local_coder is None  # rejected
    assert payload.complexity is None  # rejected
    assert payload.skip_review is True  # valid
    assert len(warnings) == 2


def test_invalid_complexity_enum_value():
    """A string that's not in the enum produces a warning."""
    raw = {"complexity": "medium"}

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.complexity is None
    assert len(warnings) == 1
    assert "'complexity' must be one of" in warnings[0]


def test_context_files_exceeds_max():
    """More than 20 context files produces a warning."""
    raw = {"contextFiles": [f"file{i}.py" for i in range(25)]}

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.context_files is None
    assert len(warnings) == 1
    assert "at most 20 entries" in warnings[0]


def test_context_files_non_string_elements():
    """Non-string elements in contextFiles produce a warning."""
    raw = {"contextFiles": ["valid.py", 123, "also_valid.py"]}

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.context_files is None
    assert len(warnings) == 1
    assert "contextFiles[1]" in warnings[0]


def test_scope_exceeds_max_length():
    """Scope string exceeding 500 chars produces a warning."""
    raw = {"scope": "x" * 501}

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.scope is None
    assert len(warnings) == 1
    assert "at most 500 characters" in warnings[0]


def test_none_input_returns_none():
    """None input returns (None, [])."""
    payload, warnings = validate_and_process_hints(None)

    assert payload is None
    assert warnings == []


def test_non_dict_input_returns_none_with_warning():
    """Non-dict input returns (None, [warning])."""
    payload, warnings = validate_and_process_hints("not a dict")

    assert payload is None
    assert len(warnings) == 1
    assert "expected object" in warnings[0]


def test_empty_dict_returns_empty_payload():
    """Empty dict returns a HintsPayload with all None fields."""
    payload, warnings = validate_and_process_hints({})

    assert payload is not None
    assert payload.prefer_local_coder is None
    assert payload.complexity is None
    assert payload.context_files is None
    assert payload.skip_review is None
    assert payload.scope is None
    assert warnings == []


def test_all_invalid_returns_empty_payload_with_warnings():
    """When all fields are invalid, returns HintsPayload with all None fields."""
    raw = {
        "preferLocalCoder": "yes",
        "complexity": 99,
        "contextFiles": "not_a_list",
        "skipReview": 1,
        "scope": 12345,
    }

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.prefer_local_coder is None
    assert payload.complexity is None
    assert payload.context_files is None
    assert payload.skip_review is None
    assert payload.scope is None
    assert len(warnings) == 5


def test_valid_entries_processed_despite_invalid_ones():
    """Valid entries are processed even when other entries are invalid."""
    raw = {
        "preferLocalCoder": True,
        "complexity": "not_valid_enum",
        "contextFiles": ["good.py"],
        "skipReview": "nope",
        "scope": "validate_email",
    }

    payload, warnings = validate_and_process_hints(raw)

    assert payload is not None
    assert payload.prefer_local_coder is True
    assert payload.complexity is None  # invalid enum
    assert payload.context_files == ["good.py"]
    assert payload.skip_review is None  # invalid type
    assert payload.scope == "validate_email"
    assert len(warnings) == 2
