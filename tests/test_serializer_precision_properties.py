"""Property tests for serialization float precision.

Feature: e2e-audio-validation, Property 12: Serialization float precision
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from audio_validation.models import TranscriptionResult, Segment, WordTimestamp
from audio_validation.serializer import TranscriptionSerializer


# --- Hypothesis Strategies ---

word_timestamps = st.builds(
    WordTimestamp,
    word=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    start=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

segments = st.builds(
    Segment,
    text=st.text(min_size=1, max_size=200),
    start=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
    words=st.lists(word_timestamps, min_size=0, max_size=20),
)

transcription_results = st.builds(
    TranscriptionResult,
    segments=st.lists(segments, min_size=0, max_size=10),
    language=st.sampled_from(["en", "es", "fr", "de", "ja"]),
    duration=st.floats(min_value=0.1, max_value=600.0, allow_nan=False, allow_infinity=False),
    model=st.sampled_from(["tiny", "base", "small"]),
)


@given(result=transcription_results)
@settings(max_examples=100)
def test_serialization_float_precision(result):
    """Serialized JSON has at most 6 decimal places for every float value.

    **Validates: Requirements 8.1**
    """
    json_str = TranscriptionSerializer.to_json(result)

    # Find all numbers with a decimal point in the JSON string
    decimal_numbers = re.findall(r"\d+\.\d+", json_str)

    for num_str in decimal_numbers:
        decimal_places = len(num_str.split(".")[1])
        assert decimal_places <= 6, (
            f"Float {num_str} has {decimal_places} decimal places (max allowed: 6)"
        )
