"""Property tests for deserialization error reporting.

Feature: e2e-audio-validation, Property 14: Deserialization error reporting
"""

import json

import pytest
from hypothesis import given, settings, assume
import hypothesis.strategies as st

from audio_validation.serializer import TranscriptionSerializer
from audio_validation.errors import ParseError


class TestDeserializationErrorReporting:
    """**Validates: Requirements 8.4**

    For any JSON string that is malformed or missing required TranscriptionResult
    fields, the deserializer SHALL raise a ParseError that includes the name of the
    first missing or invalid field and whether the failure is due to absence, wrong
    type, or invalid value.
    """

    @given(text=st.text(min_size=0, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_malformed_json_raises_parse_error(self, text: str) -> None:
        """Malformed JSON strings raise ParseError with field_name='json' and reason='invalid_value'."""
        # Filter out strings that happen to be valid JSON
        try:
            json.loads(text)
            assume(False)  # Skip if the string is valid JSON
        except (json.JSONDecodeError, ValueError):
            pass  # Good — this is malformed JSON

        with pytest.raises(ParseError) as exc_info:
            TranscriptionSerializer.from_json(text)

        assert exc_info.value.field_name == "json"
        assert exc_info.value.reason == "invalid_value"

    @given(field_to_remove=st.sampled_from(["segments", "language", "duration", "model"]))
    @settings(max_examples=100, deadline=None)
    def test_missing_required_fields_raises_parse_error(self, field_to_remove: str) -> None:
        """Valid JSON missing a required field raises ParseError with reason='absence'."""
        # Build a complete valid dict then remove one field
        complete_dict = {
            "segments": [],
            "language": "en",
            "duration": 5.0,
            "model": "tiny",
        }
        del complete_dict[field_to_remove]
        json_str = json.dumps(complete_dict)

        with pytest.raises(ParseError) as exc_info:
            TranscriptionSerializer.from_json(json_str)

        assert exc_info.value.field_name == field_to_remove
        assert exc_info.value.reason == "absence"

    @given(
        field_to_break=st.sampled_from(["segments", "language", "duration", "model"]),
        wrong_value=st.one_of(
            st.none(),
            st.booleans(),
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_wrong_type_fields_raises_parse_error(
        self, field_to_break: str, wrong_value: object
    ) -> None:
        """Fields with wrong types raise ParseError with reason='wrong_type'."""
        # Build a complete valid dict then replace one field with a wrong type
        complete_dict: dict = {
            "segments": [],
            "language": "en",
            "duration": 5.0,
            "model": "tiny",
        }

        # Pick a value that is definitely the wrong type for this field
        if field_to_break == "segments":
            # segments expects a list; give it a non-list
            complete_dict["segments"] = 123
        elif field_to_break == "language":
            # language expects a str; give it a non-str
            complete_dict["language"] = 123
        elif field_to_break == "duration":
            # duration expects int/float; give it a str
            complete_dict["duration"] = "not_a_number"
        elif field_to_break == "model":
            # model expects a str; give it a non-str
            complete_dict["model"] = 456

        json_str = json.dumps(complete_dict)

        with pytest.raises(ParseError) as exc_info:
            TranscriptionSerializer.from_json(json_str)

        assert exc_info.value.field_name == field_to_break
        assert exc_info.value.reason == "wrong_type"
