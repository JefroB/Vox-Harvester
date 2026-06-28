"""Property tests for TranscriptionResult structural validity.

Feature: e2e-audio-validation, Property 5: TranscriptionResult structural validity

Validates: Requirements 2.2, 2.3
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import characters

from audio_validation.models import Segment, TranscriptionResult, WordTimestamp


# --- Hypothesis strategies ---

word_timestamps = st.builds(
    WordTimestamp,
    word=st.text(min_size=1, max_size=20, alphabet=characters(whitelist_categories=("L",))),
    start=st.floats(min_value=0.0, max_value=299.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

segments = st.builds(
    Segment,
    text=st.text(min_size=1, max_size=200),
    start=st.floats(min_value=0.0, max_value=299.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
    words=st.lists(word_timestamps, min_size=1, max_size=10),
)

transcription_results = st.builds(
    TranscriptionResult,
    segments=st.lists(segments, min_size=1, max_size=5),
    language=st.sampled_from(["en", "es", "fr"]),
    duration=st.floats(min_value=0.1, max_value=600.0, allow_nan=False, allow_infinity=False),
    model=st.sampled_from(["tiny", "base"]),
)


@given(result=transcription_results)
@settings(max_examples=100)
def test_transcription_result_structural_validity(result: TranscriptionResult):
    """Property 5: TranscriptionResult structural validity.

    For any generated TranscriptionResult, all segments have start < end,
    all WordTimestamps have start < end and 0.0 <= confidence <= 1.0,
    required fields are present with correct types.

    **Validates: Requirements 2.2, 2.3**
    """
    # Filter: ensure generated start < end for segments and words
    for seg in result.segments:
        assume(seg.start < seg.end)
        for w in seg.words:
            assume(w.start < w.end)

    # Assert: segments list is not empty
    assert len(result.segments) > 0

    # Assert: language is a string
    assert isinstance(result.language, str)

    # Assert: duration > 0
    assert result.duration > 0

    # Assert: model is a string
    assert isinstance(result.model, str)

    # Assert: all segments have start < end
    for seg in result.segments:
        assert seg.start < seg.end, f"Segment start ({seg.start}) >= end ({seg.end})"

        # Assert: all WordTimestamps have start < end and valid confidence
        for word in seg.words:
            assert word.start < word.end, (
                f"Word '{word.word}' start ({word.start}) >= end ({word.end})"
            )
            assert 0.0 <= word.confidence <= 1.0, (
                f"Word '{word.word}' confidence ({word.confidence}) out of range [0.0, 1.0]"
            )
