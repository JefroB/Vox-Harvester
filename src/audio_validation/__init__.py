"""Audio validation subsystem for the Vox Harvester pipeline.

Provides audio preprocessing, transcription, relevance scoring,
and serialization for end-to-end audio content validation.
"""

from pathlib import Path

from .preprocessor import AudioPreprocessor
from .transcriber import TranscriptionService
from .scorer import RelevanceScorer
from .serializer import TranscriptionSerializer
from .stitcher import stitch_segments
from .errors import (
    AudioValidationError,
    PreprocessError,
    DependencyError,
    InvalidAudioError,
    TranscriptionTimeoutError,
    ParseError,
    RelevanceError,
)
from .models import WordTimestamp, Segment, TranscriptionResult, PreprocessResult, RelevanceResult

__all__ = [
    "AudioPreprocessor",
    "TranscriptionService",
    "RelevanceScorer",
    "TranscriptionSerializer",
    "stitch_segments",
    "AudioValidationError",
    "PreprocessError",
    "DependencyError",
    "InvalidAudioError",
    "TranscriptionTimeoutError",
    "ParseError",
    "RelevanceError",
    "WordTimestamp",
    "Segment",
    "TranscriptionResult",
    "PreprocessResult",
    "RelevanceResult",
    "validate_audio",
]


def validate_audio(source_path: Path, search_term: str, threshold: float = 0.3) -> RelevanceResult:
    """
    Validate audio content by preprocessing, transcribing, and scoring relevance.

    :param source_path: Path to the source audio file.
    :param search_term: Search term to compare against the transcription.
    :param threshold: Minimum score threshold for relevance (default 0.3).
    :return: RelevanceResult containing score and metadata.
    """
    # Create AudioPreprocessor instance
    preprocessor = AudioPreprocessor()
    preprocess_result = preprocessor.preprocess(source_path)

    # Create TranscriptionService instance
    transcriber = TranscriptionService()
    transcription_result = transcriber.transcribe(preprocess_result.output_paths[0])

    # Create RelevanceScorer with specified threshold
    scorer = RelevanceScorer(threshold=threshold)
    relevance_result = scorer.score(transcription_result, search_term)

    return relevance_result