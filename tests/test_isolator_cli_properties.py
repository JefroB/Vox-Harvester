"""Property tests for the CLI JSON output contract of isolator.py.

Feature: vocal-isolation, Property 16: CLI JSON output contract
"""

import json
from dataclasses import asdict

from hypothesis import given, settings
from hypothesis import strategies as st

from src.audio_validation.isolator import IsolationResult, IsolationError


# --- Hypothesis Strategies ---

# File-path-like strings: alphanumeric, slashes, dots, underscores, hyphens
file_path_chars = st.characters(
    whitelist_categories=("L", "N"),
    whitelist_characters="/\\._-",
)

isolation_result_fields = st.builds(
    IsolationResult,
    input_path=st.text(min_size=1, max_size=255, alphabet=file_path_chars),
    output_path=st.text(min_size=1, max_size=255, alphabet=file_path_chars),
    duration_seconds=st.floats(min_value=0.01, max_value=3600.0, allow_nan=False, allow_infinity=False),
    model_name=st.sampled_from(['htdemucs_ft', 'htdemucs']),
    device=st.sampled_from(['cuda', 'cpu']),
    processing_time_seconds=st.floats(min_value=0.01, max_value=3600.0, allow_nan=False, allow_infinity=False),
    gpu_unavailable=st.booleans(),
)

isolation_error_fields = st.builds(
    IsolationError,
    error=st.text(min_size=1, max_size=255, alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"))),
    dependency=st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N")))),
    input_path=st.text(min_size=1, max_size=255, alphabet=file_path_chars),
)


@given(isolation_result_fields)
@settings(max_examples=100)
def test_isolation_result_json_contract(result):
    """Test that IsolationResult dataclass serializes to valid JSON with correct structure.

    Validates that the CLI stdout JSON output matches the expected schema:
    - input_path (string)
    - output_path (string)
    - duration_seconds (number)
    - model_name (string)
    - device (string)
    - processing_time_seconds (number)
    - gpu_unavailable (boolean)

    **Validates: Requirements 7.3, 7.4**
    """
    # Serialize using the same pattern as CLI code: json.dumps(asdict(result))
    json_str = json.dumps(asdict(result))
    parsed = json.loads(json_str)

    # Check all required fields are present
    assert "input_path" in parsed
    assert "output_path" in parsed
    assert "duration_seconds" in parsed
    assert "model_name" in parsed
    assert "device" in parsed
    assert "processing_time_seconds" in parsed
    assert "gpu_unavailable" in parsed

    # Check field types
    assert isinstance(parsed["input_path"], str)
    assert isinstance(parsed["output_path"], str)
    assert isinstance(parsed["duration_seconds"], (int, float))
    assert isinstance(parsed["model_name"], str)
    assert isinstance(parsed["device"], str)
    assert isinstance(parsed["processing_time_seconds"], (int, float))
    assert isinstance(parsed["gpu_unavailable"], bool)

    # Check numeric values are positive
    assert parsed["duration_seconds"] > 0
    assert parsed["processing_time_seconds"] > 0


@given(isolation_error_fields)
@settings(max_examples=100)
def test_isolation_error_json_contract(error):
    """Test that IsolationError dataclass serializes to valid JSON with correct structure.

    Validates that the CLI stderr JSON output matches the expected schema:
    - error (string)
    - dependency (string or null)
    - input_path (string)

    **Validates: Requirements 7.3, 7.4**
    """
    # Serialize using the same pattern as CLI code: json.dumps(asdict(error))
    json_str = json.dumps(asdict(error))
    parsed = json.loads(json_str)

    # Check all required fields are present
    assert "error" in parsed
    assert "dependency" in parsed
    assert "input_path" in parsed

    # Check field types
    assert isinstance(parsed["error"], str)
    assert isinstance(parsed["input_path"], str)
    assert parsed["dependency"] is None or isinstance(parsed["dependency"], str)

    # Check error is not empty
    assert len(parsed["error"]) > 0


@given(st.one_of(isolation_result_fields, isolation_error_fields))
@settings(max_examples=100)
def test_cli_output_contract_both_paths(dataclass_instance):
    """Test that both success and failure cases produce valid JSON with correct structure.

    Tests the complete CLI output contract for both successful and failed executions.

    **Validates: Requirements 7.3, 7.4**
    """
    # Serialize using the same pattern as CLI code
    json_str = json.dumps(asdict(dataclass_instance))
    parsed = json.loads(json_str)

    # Validate success case structure
    if isinstance(dataclass_instance, IsolationResult):
        assert "input_path" in parsed
        assert "output_path" in parsed
        assert "duration_seconds" in parsed
        assert "model_name" in parsed
        assert "device" in parsed
        assert "processing_time_seconds" in parsed
        assert "gpu_unavailable" in parsed

        # Check types for success case
        assert isinstance(parsed["input_path"], str)
        assert isinstance(parsed["output_path"], str)
        assert isinstance(parsed["duration_seconds"], (int, float))
        assert isinstance(parsed["model_name"], str)
        assert isinstance(parsed["device"], str)
        assert isinstance(parsed["processing_time_seconds"], (int, float))
        assert isinstance(parsed["gpu_unavailable"], bool)

        # Check numeric values are positive
        assert parsed["duration_seconds"] > 0
        assert parsed["processing_time_seconds"] > 0

    else:
        # This is an IsolationError
        assert isinstance(dataclass_instance, IsolationError)
        assert "error" in parsed
        assert "dependency" in parsed
        assert "input_path" in parsed

        # Check types for error case
        assert isinstance(parsed["error"], str)
        assert isinstance(parsed["input_path"], str)
        assert parsed["dependency"] is None or isinstance(parsed["dependency"], str)

        # Check error is not empty
        assert len(parsed["error"]) > 0