"""Property tests for relevance scoring formula correctness.

Feature: e2e-audio-validation, Property 8: Relevance score formula correctness
"""

from hypothesis import given, settings, assume
import re
from nltk.stem import PorterStemmer
from audio_validation.scorer import RelevanceScorer
from audio_validation.models import Segment, TranscriptionResult

# Strategy for generating text with alphabetic words
def generate_text_with_words(min_words=1, max_words=10):
    """Generate text containing alphabetic words."""
    from hypothesis.strategies import text, integers
    return text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ", 
                min_size=min_words * 2, max_size=max_words * 10).filter(
        lambda t: any(c.isalpha() for c in t)
    )

# Strategy for segments with text containing alphabetic words
segments_strategy = generate_text_with_words().map(
    lambda text: Segment(text=text, start=0.0, end=1.0)
)

# Strategy for transcription results with at least 1 segment
transcription_result_strategy = segments_strategy.map(
    lambda seg: TranscriptionResult(
        segments=[seg], 
        language="en", 
        duration=1.0, 
        model="medium"
    )
)

# Strategy for search terms that produce at least 1 token
def valid_search_term():
    """Generate search terms that produce at least 1 token."""
    from hypothesis.strategies import text
    return text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ", 
                min_size=3).filter(
        lambda t: any(c.isalnum() for c in t)
    )

@given(
    transcription_result_strategy,
    valid_search_term()
)
@settings(max_examples=100)
def test_relevance_score_formula(transcript, search_term):
    """Test that relevance scoring formula produces correct results.

    **Validates: Requirements 3.1, 3.3, 3.4, 3.5**
    """
    # Skip cases where search term normalizes to empty
    assume(search_term.strip())
    
    scorer = RelevanceScorer(threshold=0.3)
    result = scorer.score(transcript, search_term)
    
    # Compute expected score using oracle implementation
    stemmer = PorterStemmer()
    
    # Normalize search term
    search_text = search_term.lower()
    search_text = re.sub(r'[^a-z0-9]', ' ', search_text)
    search_tokens = [token for token in search_text.split() if token]
    search_stems = [stemmer.stem(token) for token in search_tokens]
    
    # Check if search term produces valid tokens
    assume(search_stems)
    
    # Normalize transcript text
    full_transcript_text = " ".join(segment.text for segment in transcript.segments)
    transcript_text = full_transcript_text.lower()
    transcript_text = re.sub(r'[^a-z0-9]', ' ', transcript_text)
    transcript_tokens = [token for token in transcript_text.split() if token]
    transcript_stems = [stemmer.stem(token) for token in transcript_tokens]
    
    # Compute matched tokens
    matched = set(search_stems) & set(transcript_stems)
    
    # Calculate expected score
    expected_score = len(matched) / len(set(search_stems)) if search_stems else 0.0
    
    # Assertions
    assert abs(result.score - expected_score) < 1e-9, f"Score mismatch: {result.score} != {expected_score}"
    assert 0.0 <= result.score <= 1.0, f"Score out of range: {result.score}"
    assert result.is_relevant == (result.score > 0.3), f"Relevance mismatch: score={result.score}, is_relevant={result.is_relevant}"