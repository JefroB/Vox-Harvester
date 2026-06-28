"""Error hierarchy for the audio validation subsystem.

All errors inherit from AudioValidationError, the base exception for this package.
"""

from pathlib import Path


class AudioValidationError(Exception):
    """Base error for the audio validation subsystem."""

    pass


class PreprocessError(AudioValidationError):
    """Raised when audio preprocessing fails."""

    def __init__(self, message: str, file_path: Path):
        self.file_path = file_path
        super().__init__(f"{message}: {file_path}")


class DependencyError(AudioValidationError):
    """Raised when a required dependency is missing."""

    def __init__(self, dependency_name: str, reason: str):
        self.dependency_name = dependency_name
        self.reason = reason
        super().__init__(f"Missing dependency '{dependency_name}': {reason}")


class InvalidAudioError(AudioValidationError):
    """Raised when input file is not valid audio."""

    def __init__(self, file_path: Path, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Invalid audio '{file_path}': {reason}")


class TranscriptionTimeoutError(AudioValidationError):
    """Raised when Whisper inference exceeds timeout."""

    def __init__(self, file_path: Path, elapsed_seconds: float):
        self.file_path = file_path
        self.elapsed_seconds = elapsed_seconds
        super().__init__(f"Transcription timeout after {elapsed_seconds:.1f}s: {file_path}")


class ParseError(AudioValidationError):
    """Raised when JSON deserialization fails."""

    def __init__(self, field_name: str, reason: str):
        self.field_name = field_name
        self.reason = reason  # "absence" | "wrong_type" | "invalid_value"
        super().__init__(f"Parse error on field '{field_name}': {reason}")


class RelevanceError(AudioValidationError):
    """Raised when relevance scoring cannot proceed."""

    pass
