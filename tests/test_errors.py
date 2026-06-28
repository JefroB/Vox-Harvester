"""Unit tests for the audio_validation error hierarchy."""

from pathlib import Path

from audio_validation.errors import (
    AudioValidationError,
    DependencyError,
    InvalidAudioError,
    ParseError,
    PreprocessError,
    RelevanceError,
    TranscriptionTimeoutError,
)


class TestAudioValidationError:
    """Base error class tests."""

    def test_is_exception(self):
        err = AudioValidationError("test message")
        assert isinstance(err, Exception)

    def test_message(self):
        err = AudioValidationError("something went wrong")
        assert str(err) == "something went wrong"


class TestPreprocessError:
    """PreprocessError tests."""

    def test_inherits_base(self):
        err = PreprocessError("decode failed", Path("/tmp/test.wav"))
        assert isinstance(err, AudioValidationError)

    def test_file_path_attribute(self):
        p = Path("/audio/sample.wav")
        err = PreprocessError("cannot read", p)
        assert err.file_path == p

    def test_message_format(self):
        p = Path("/audio/sample.wav")
        err = PreprocessError("decode failed", p)
        assert str(err) == f"decode failed: {p}"


class TestDependencyError:
    """DependencyError tests."""

    def test_inherits_base(self):
        err = DependencyError("openai-whisper", "not installed")
        assert isinstance(err, AudioValidationError)

    def test_attributes(self):
        err = DependencyError("ffmpeg", "binary not found")
        assert err.dependency_name == "ffmpeg"
        assert err.reason == "binary not found"

    def test_message_format(self):
        err = DependencyError("openai-whisper", "import failed")
        assert str(err) == "Missing dependency 'openai-whisper': import failed"


class TestInvalidAudioError:
    """InvalidAudioError tests."""

    def test_inherits_base(self):
        err = InvalidAudioError(Path("/tmp/bad.wav"), "corrupt header")
        assert isinstance(err, AudioValidationError)

    def test_attributes(self):
        p = Path("/tmp/bad.wav")
        err = InvalidAudioError(p, "not a WAV file")
        assert err.file_path == p
        assert err.reason == "not a WAV file"

    def test_message_format(self):
        p = Path("/tmp/bad.wav")
        err = InvalidAudioError(p, "corrupt header")
        assert str(err) == f"Invalid audio '{p}': corrupt header"


class TestTranscriptionTimeoutError:
    """TranscriptionTimeoutError tests."""

    def test_inherits_base(self):
        err = TranscriptionTimeoutError(Path("/tmp/long.wav"), 125.3)
        assert isinstance(err, AudioValidationError)

    def test_attributes(self):
        p = Path("/tmp/long.wav")
        err = TranscriptionTimeoutError(p, 130.5)
        assert err.file_path == p
        assert err.elapsed_seconds == 130.5

    def test_message_format(self):
        p = Path("/tmp/long.wav")
        err = TranscriptionTimeoutError(p, 125.3)
        assert str(err) == f"Transcription timeout after 125.3s: {p}"


class TestParseError:
    """ParseError tests."""

    def test_inherits_base(self):
        err = ParseError("segments", "absence")
        assert isinstance(err, AudioValidationError)

    def test_attributes(self):
        err = ParseError("duration", "wrong_type")
        assert err.field_name == "duration"
        assert err.reason == "wrong_type"

    def test_message_format(self):
        err = ParseError("language", "absence")
        assert str(err) == "Parse error on field 'language': absence"

    def test_valid_reasons(self):
        for reason in ("absence", "wrong_type", "invalid_value"):
            err = ParseError("field", reason)
            assert err.reason == reason


class TestRelevanceError:
    """RelevanceError tests."""

    def test_inherits_base(self):
        err = RelevanceError("no valid tokens")
        assert isinstance(err, AudioValidationError)

    def test_message(self):
        err = RelevanceError("search term is empty")
        assert str(err) == "search term is empty"


class TestInheritanceHierarchy:
    """All errors can be caught with the base class."""

    def test_catch_all_with_base(self):
        errors = [
            PreprocessError("fail", Path("/tmp/x.wav")),
            DependencyError("whisper", "missing"),
            InvalidAudioError(Path("/tmp/y.wav"), "corrupt"),
            TranscriptionTimeoutError(Path("/tmp/z.wav"), 120.0),
            ParseError("segments", "absence"),
            RelevanceError("no tokens"),
        ]
        for err in errors:
            try:
                raise err
            except AudioValidationError:
                pass  # All should be caught here
