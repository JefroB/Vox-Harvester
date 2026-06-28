"""Property tests for empty search term rejection.

Feature: e2e-audio-validation
Property 10: Empty search term rejection

**Validates: Requirements 3.6**
"""

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import characters

from audio_validation.scorer import RelevanceScorer
from audio_validation.errors import RelevanceError
from audio_validation.models import Segment, TranscriptionResult


@given(
    search_term=st.one_of(
        st.text(
            alphabet=characters(whitelist_categories=('P', 'S', 'Z')),
            min_size=0,
            max_size=50,
        ),
        st.just(''),
    )
)
@settings(max_examples=100)
def test_empty_search_term_rejected(search_term):
    """Property 10: Empty search term rejection.

    Generate strings with no alphanumeric characters (all punctuation/whitespace/empty).
    Assert: RelevanceError raised indicating no valid tokens.
    """
    scorer = RelevanceScorer()
    transcript = TranscriptionResult(
        segments=[Segment(text='hello world', start=0.0, end=1.0)],
        language='en',
        duration=1.0,
        model='tiny',
    )

    with pytest.raises(RelevanceError):
        scorer.score(transcript, search_term)
