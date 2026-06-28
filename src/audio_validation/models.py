"""Data models for the audio validation subsystem.

Defines the core dataclasses used across the preprocessing, transcription,
scoring, and serialization components.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WordTimestamp:
    """A single word with timing and confidence from Whisper output."""

    word: str
    start: float  # seconds
    end: float  # seconds
    confidence: float  # 0.0 to 1.0


@dataclass
class Segment:
    """A transcription segment containing text, timing, and word-level detail."""

    text: str
    start: float
    end: float
    words: list[WordTimestamp] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    """Complete transcription output from the Transcription Service."""

    segments: list[Segment]
    language: str
    duration: float  # total audio duration in seconds
    model: str  # e.g., "tiny"


@dataclass
class PreprocessResult:
    """Result of audio preprocessing via FFmpeg."""

    output_paths: list[Path]  # One path for short files, multiple for chunked
    sample_rate: int  # Always 16000
    channels: int  # Always 1
    bit_depth: int  # Always 16
    duration_seconds: float  # Total duration of source


@dataclass
class RelevanceResult:
    """Result of comparing a transcript against a search term."""

    score: float  # 0.0 to 1.0
    is_relevant: bool  # score > threshold
    matched_tokens: list[str]
    search_tokens: list[str]
    transcript_tokens: list[str]
