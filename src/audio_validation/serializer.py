"""Serializer for transcription results.

Provides JSON serialization/deserialization and human-readable pretty-printing
for TranscriptionResult objects used in the audio validation pipeline.
"""

import json
from typing import Any

from .errors import ParseError
from .models import TranscriptionResult, Segment, WordTimestamp


def _round_floats(obj: Any) -> Any:
    """Recursively round all floats in a nested structure to 6 decimal places."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item) for item in obj]
    return obj


def _to_dict(obj: Any) -> Any:
    """Convert a dataclass (or nested dataclasses) to a plain dict."""
    if hasattr(obj, "__dict__") and hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    return obj


class TranscriptionSerializer:
    """JSON serialization/deserialization for TranscriptionResult."""

    @staticmethod
    def to_json(result: TranscriptionResult) -> str:
        """Serialize a TranscriptionResult to JSON with ≤6 decimal places for floats.

        Args:
            result: The transcription result to serialize.

        Returns:
            JSON string representation of the transcription result.
        """
        data = _round_floats(_to_dict(result))
        return json.dumps(data)

    @staticmethod
    def from_json(json_str: str) -> TranscriptionResult:
        """Deserialize a JSON string to a TranscriptionResult.

        Raises ParseError with field name and reason ("absence", "wrong_type",
        "invalid_value") on failure.

        Args:
            json_str: JSON string representation of a transcription result.

        Returns:
            Reconstructed TranscriptionResult object.

        Raises:
            ParseError: If JSON is invalid or required fields are missing/incorrect.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ParseError("json", "invalid_value") from e

        # Validate required top-level fields
        required_fields = ["segments", "language", "duration", "model"]
        for field in required_fields:
            if field not in data:
                raise ParseError(field, "absence")

        # Validate types
        if not isinstance(data["segments"], list):
            raise ParseError("segments", "wrong_type")
        if not isinstance(data["language"], str):
            raise ParseError("language", "wrong_type")
        if not isinstance(data["duration"], (int, float)):
            raise ParseError("duration", "wrong_type")
        if not isinstance(data["model"], str):
            raise ParseError("model", "wrong_type")

        # Reconstruct segments
        segments = []
        for segment_data in data["segments"]:
            if not isinstance(segment_data, dict):
                raise ParseError("segments", "wrong_type")

            required_segment_fields = ["text", "start", "end", "words"]
            for field in required_segment_fields:
                if field not in segment_data:
                    raise ParseError(f"segments[{field}]", "absence")

            # Validate segment types
            if not isinstance(segment_data["text"], str):
                raise ParseError("segments.text", "wrong_type")
            if not isinstance(segment_data["start"], (int, float)):
                raise ParseError("segments.start", "wrong_type")
            if not isinstance(segment_data["end"], (int, float)):
                raise ParseError("segments.end", "wrong_type")
            if not isinstance(segment_data["words"], list):
                raise ParseError("segments.words", "wrong_type")

            # Reconstruct words
            words = []
            for word_data in segment_data["words"]:
                if not isinstance(word_data, dict):
                    raise ParseError("segments.words", "wrong_type")

                required_word_fields = ["word", "start", "end", "confidence"]
                for field in required_word_fields:
                    if field not in word_data:
                        raise ParseError(f"segments.words[{field}]", "absence")

                # Validate word types
                if not isinstance(word_data["word"], str):
                    raise ParseError("segments.words.word", "wrong_type")
                if not isinstance(word_data["start"], (int, float)):
                    raise ParseError("segments.words.start", "wrong_type")
                if not isinstance(word_data["end"], (int, float)):
                    raise ParseError("segments.words.end", "wrong_type")
                if not isinstance(word_data["confidence"], (int, float)):
                    raise ParseError("segments.words.confidence", "wrong_type")

                words.append(
                    WordTimestamp(
                        word=word_data["word"],
                        start=word_data["start"],
                        end=word_data["end"],
                        confidence=word_data["confidence"],
                    )
                )

            segments.append(
                Segment(
                    text=segment_data["text"],
                    start=segment_data["start"],
                    end=segment_data["end"],
                    words=words,
                )
            )

        return TranscriptionResult(
            segments=segments,
            language=data["language"],
            duration=float(data["duration"]),
            model=data["model"],
        )

    @staticmethod
    def pretty_print(result: TranscriptionResult) -> str:
        """Format as human-readable text: [<start>s-<end>s] <text> per segment.

        Timestamps use 1 decimal place. Segments are separated by newlines.
        Returns empty string for empty segments.

        Args:
            result: The transcription result to format.

        Returns:
            Formatted string with segments, or empty string if no segments.
        """
        if not result.segments:
            return ""

        formatted_segments = []
        for segment in result.segments:
            formatted_segments.append(
                f"[{segment.start:.1f}s-{segment.end:.1f}s] {segment.text}"
            )

        return "\n".join(formatted_segments)