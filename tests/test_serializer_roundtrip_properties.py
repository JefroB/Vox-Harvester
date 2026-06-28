"""Property tests for serialization round-trip preservation.

Feature: e2e-audio-validation, Property 11: Serialization round-trip preservation
"""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from audio_validation.models import Segment, TranscriptionResult, WordTimestamp
from audio_validation.serializer import TranscriptionSerializer


# --- Hypothesis Strategies (from design doc) ---

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
    words=st.lists(word_timestamps, min_size=1, max_size=20),
)

transcription_results = st.builds(
    TranscriptionResult,
    segments=st.lists(segments, min_size=0, max_size=10),
    language=st.sampled_from(["en", "es", "fr", "de", "ja"]),
    duration=st.floats(min_value=0.1, max_value=600.0, allow_nan=False, allow_infinity=False),
    model=st.sampled_from(["tiny", "base", "small"]),
)


@given(transcription_results)
@settings(max_examples=100)
def test_serialization_roundtrip_preserves_fields(result):
    """Serialize then deserialize a TranscriptionResult; verify field preservation.

    String and integer fields must be identical. Float fields must match within 1e-6.

    **Validates: Requirements 8.2, 8.3**
    """
    json_str = TranscriptionSerializer.to_json(result)
    restored = TranscriptionSerializer.from_json(json_str)

    # Top-level string fields are identical
    assert restored.language == result.language
    assert restored.model == result.model

    # Top-level float field matches within tolerance
    assert math.isclose(restored.duration, result.duration, abs_tol=1e-6), (
        f"duration mismatch: {restored.duration} vs {result.duration}"
    )

    # Same number of segments
    assert len(restored.segments) == len(result.segments)

    for orig_seg, rest_seg in zip(result.segments, restored.segments):
        # Segment string field identical
        assert rest_seg.text == orig_seg.text

        # Segment float fields within tolerance
        assert math.isclose(rest_seg.start, orig_seg.start, abs_tol=1e-6), (
            f"segment start mismatch: {rest_seg.start} vs {orig_seg.start}"
        )
        assert math.isclose(rest_seg.end, orig_seg.end, abs_tol=1e-6), (
            f"segment end mismatch: {rest_seg.end} vs {orig_seg.end}"
        )

        # Same number of words per segment
        assert len(rest_seg.words) == len(orig_seg.words)

        for orig_word, rest_word in zip(orig_seg.words, rest_seg.words):
            # Word string field identical
            assert rest_word.word == orig_word.word

            # Word float fields within tolerance
            assert math.isclose(rest_word.start, orig_word.start, abs_tol=1e-6), (
                f"word start mismatch: {rest_word.start} vs {orig_word.start}"
            )
            assert math.isclose(rest_word.end, orig_word.end, abs_tol=1e-6), (
                f"word end mismatch: {rest_word.end} vs {orig_word.end}"
            )
            assert math.isclose(rest_word.confidence, orig_word.confidence, abs_tol=1e-6), (
                f"word confidence mismatch: {rest_word.confidence} vs {orig_word.confidence}"
            )
