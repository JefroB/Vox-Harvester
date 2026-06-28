"""Relevance scoring for audio transcriptions."""

import re

from nltk.stem import PorterStemmer

from .errors import RelevanceError
from .models import TranscriptionResult, RelevanceResult


class RelevanceScorer:
    """Scores the relevance of a transcription to a search term."""

    def __init__(self, threshold: float = 0.3):
        """
        Initialize the relevance scorer.

        :param threshold: Minimum score threshold for relevance (0.0-1.0). Defaults to 0.3.
        :raises ValueError: If threshold is not in range [0.0, 1.0].
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        
        self.threshold = threshold
        self._stemmer = PorterStemmer()

    def _normalize_and_stem(self, text: str) -> list[str]:
        """
        Normalize text by lowercasing, removing non-alphanumeric characters,
        splitting on whitespace, and applying Porter stemming.

        :param text: Input text to normalize
        :return: List of stemmed tokens
        """
        # Convert to lowercase
        text = text.lower()
        
        # Replace non-alphanumeric characters with spaces
        text = re.sub(r'[^a-z0-9]', ' ', text)
        
        # Split on whitespace and filter out empty strings
        tokens = [token for token in text.split() if token]
        
        # Apply Porter stemming
        stemmed_tokens = [self._stemmer.stem(token) for token in tokens]
        
        return stemmed_tokens

    def score(self, transcript: TranscriptionResult, search_term: str) -> RelevanceResult:
        """
        Score the relevance of a transcription to a search term.

        :param transcript: The transcription result to score
        :param search_term: The search term to compare against
        :return: RelevanceResult containing score and metadata
        :raises RelevanceError: If search term produces no valid tokens
        """
        # Normalize search term
        search_tokens = self._normalize_and_stem(search_term)
        
        # Check if any tokens were produced
        if not search_tokens:
            raise RelevanceError("Search term produced no valid tokens for comparison")
        
        # Extract all text from transcript segments
        full_transcript_text = " ".join(segment.text for segment in transcript.segments)
        
        # Normalize transcript text
        transcript_tokens = self._normalize_and_stem(full_transcript_text)
        
        # Compute matched tokens
        matched = set(search_tokens) & set(transcript_tokens)
        
        # Calculate score
        search_token_set = set(search_tokens)
        score = len(matched) / len(search_token_set) if search_token_set else 0.0
        
        # Determine relevance
        is_relevant = score > self.threshold
        
        return RelevanceResult(
            score=score,
            is_relevant=is_relevant,
            matched_tokens=sorted(list(matched)),
            search_tokens=sorted(list(search_token_set)),
            transcript_tokens=sorted(list(set(transcript_tokens)))
        )