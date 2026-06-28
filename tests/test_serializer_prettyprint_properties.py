"""Property tests for pretty-print format correctness.

Feature: e2e-audio-validation, Property 13: Pretty-print format correctness
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from audio_validation.models import Segment, TranscriptionResult
from audio_validation.serializer import TranscriptionSerializer


# Strategy for generating segments with non-empty single-line text
# (newlines in text would split into extra output lines, which is expected
# behavior but would break the line-count assertion)
segments_strategy = st.builds(
    Segment,
    text=st.text(
        min_size=1, max_size=50,
        alphabet=st.characters(blacklist_categories=("Cc",)),  # exclude control chars (incl. \n)
    ),
    start=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    end=st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
)

# Strategy for TranscriptionResult with 1-10 segments
transcription_result_strategy = st.builds(
    TranscriptionResult,
    segments=st.lists(segments_strategy, min_size=1, max_size=10),
    language=st.sampled_from(["en", "es", "fr", "de", "ja"]),
    duration=st.floats(min_value=0.1, max_value=600.0, allow_nan=False, allow_infinity=False),
    model=st.sampled_from(["tiny", "base", "small"]),
)

# Regex pattern for each pretty-print line: [<digits>.<1digit>s-<digits>.<1digit>s] <text>
LINE_PATTERN = re.compile(r"^\[\d+\.\d{1}s-\d+\.\d{1}s\] .+$")


@given(transcription_result_strategy)
@settings(max_examples=100)
def test_pretty_print_line_count_and_format(result):
    """Output has exactly N lines, each matching [<start>s-<end>s] <text> with 1 decimal place.

    **Validates: Requirements 8.5, 8.6**
    """
    output = TranscriptionSerializer.pretty_print(result)
    lines = output.split("\n")

    n_segments = len(result.segments)
    assert len(lines) == n_segments, (
        f"Expected {n_segments} lines, got {len(lines)}"
    )

    for i, line in enumerate(lines):
        assert LINE_PATTERN.match(line), (
            f"Line {i} does not match expected pattern: {line!r}"
        )


def test_pretty_print_empty_segments():
    """Empty segments produce an empty string.

    **Validates: Requirements 8.5, 8.6**
    """
    result = TranscriptionResult(
        segments=[],
        language="en",
        duration=0.0,
        model="tiny",
    )
    output = TranscriptionSerializer.pretty_print(result)
    assert output == ""
