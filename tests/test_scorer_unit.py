"""Unit tests for the Relevance Scorer.

Validates: Requirements 6.2
"""

import pytest

from audio_validation.scorer import RelevanceScorer
from audio_validation.models import TranscriptionResult, Segment


def test_score_zero_when_no_match():
    """Score is 0.0 when no search tokens appear in the transcript."""
    scorer = RelevanceScorer()

    segment = Segment(text="apple banana cherry", start=0.0, end=3.0)
    transcript = TranscriptionResult(
        segments=[segment],
        language="en",
        duration=3.0,
        model="tiny",
    )

    result = scorer.score(transcript, "xyz quantum")

    assert result.score == 0.0
    assert result.is_relevant is False


def test_score_one_when_all_match():
    """Score is 1.0 when all search tokens match transcript tokens."""
    scorer = RelevanceScorer()

    segment = Segment(text="motivational speech inspiring", start=0.0, end=3.0)
    transcript = TranscriptionResult(
        segments=[segment],
        language="en",
        duration=3.0,
        model="tiny",
    )

    result = scorer.score(transcript, "motivational speech")

    assert result.score == 1.0
    assert result.is_relevant is True


def test_partial_overlap_between_zero_and_one():
    """Partial overlap returns a score strictly between 0.0 and 1.0."""
    scorer = RelevanceScorer()

    segment = Segment(text="the quick brown fox jumps", start=0.0, end=3.0)
    transcript = TranscriptionResult(
        segments=[segment],
        language="en",
        duration=3.0,
        model="tiny",
    )

    # "quick" and "fox" match, "dog" does not → 2/3 ≈ 0.67
    result = scorer.score(transcript, "quick fox dog")

    assert 0.0 < result.score < 1.0
    assert round(result.score, 2) == 0.67


def test_threshold_configuration():
    """Custom threshold changes the is_relevant determination."""
    segment = Segment(text="hello world", start=0.0, end=2.0)
    transcript = TranscriptionResult(
        segments=[segment],
        language="en",
        duration=2.0,
        model="tiny",
    )

    # Score is 2/3 ≈ 0.67. With threshold=0.8, is_relevant should be False.
    scorer_high = RelevanceScorer(threshold=0.8)
    result_high = scorer_high.score(transcript, "hello world goodbye")
    assert result_high.is_relevant is False

    # With threshold=0.5, is_relevant should be True.
    scorer_low = RelevanceScorer(threshold=0.5)
    result_low = scorer_low.score(transcript, "hello world goodbye")
    assert result_low.is_relevant is True
