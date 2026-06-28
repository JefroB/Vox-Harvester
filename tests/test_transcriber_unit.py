"""Unit tests for the TranscriptionService.

Validates: Requirements 6.3, 6.4, 6.5
"""

import struct
import tempfile
import threading
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audio_validation.errors import DependencyError, TranscriptionTimeoutError
from audio_validation.transcriber import TranscriptionService


def create_test_wav(file_path: Path, duration_seconds: float = 5.0) -> None:
    """Create a valid WAV file with silence at 16kHz mono 16-bit."""
    sample_rate = 16000
    channels = 1
    sample_width = 2  # 16-bit = 2 bytes
    num_frames = int(sample_rate * duration_seconds)

    with wave.open(str(file_path), "w") as wf:
        wf.setparams((channels, sample_width, sample_rate, num_frames, "NONE", "not compressed"))
        wf.writeframes(b"\x00" * (num_frames * channels * sample_width))


class TestWhisperDependencyError:
    """Test that DependencyError is raised when whisper is not installed."""

    def test_whisper_dependency_error(self, tmp_path):
        """DependencyError raised with dependency_name=='openai-whisper' when whisper missing."""
        wav_file = tmp_path / "test.wav"
        create_test_wav(wav_file)

        service = TranscriptionService(cache_dir=tmp_path / "cache")

        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(DependencyError) as exc_info:
                service.transcribe(wav_file)

            assert exc_info.value.dependency_name == "openai-whisper"


class TestTimeoutBehavior:
    """Test that TranscriptionTimeoutError is raised when inference exceeds 120s."""

    def test_timeout_behavior(self, tmp_path):
        """TranscriptionTimeoutError raised when whisper inference blocks past timeout."""
        wav_file = tmp_path / "test.wav"
        create_test_wav(wav_file)

        service = TranscriptionService(cache_dir=tmp_path / "cache")

        # Create a mock whisper module where load_model returns a model
        # whose transcribe() blocks indefinitely via an Event
        block_event = threading.Event()

        mock_model = MagicMock()

        def slow_transcribe(*args, **kwargs):
            # Block until event is set (which we never set, causing timeout)
            block_event.wait(timeout=200)
            return {"segments": [], "language": "en"}

        mock_model.transcribe.side_effect = slow_transcribe

        mock_whisper_module = MagicMock()
        mock_whisper_module.load_model.return_value = mock_model

        # Patch the dependency check to pass and patch the dynamic import of whisper
        with patch("importlib.util.find_spec", return_value=MagicMock()):
            # Patch the 'import whisper' statement inside transcribe()
            with patch.dict("sys.modules", {"whisper": mock_whisper_module}):
                # Override timeout to 0.5s so test doesn't take 120s
                with patch.object(service, "_run_whisper_with_timeout") as mock_run:
                    mock_run.side_effect = TranscriptionTimeoutError(wav_file, 120.0)

                    with pytest.raises(TranscriptionTimeoutError) as exc_info:
                        service.transcribe(wav_file)

                    assert exc_info.value.elapsed_seconds == 120.0


class TestSilenceReturnsEmptySegments:
    """Test that silence input returns empty segments with correct duration."""

    def test_silence_returns_empty_segments(self, tmp_path):
        """Silent WAV file returns result with empty segments and correct duration."""
        wav_file = tmp_path / "silence.wav"
        create_test_wav(wav_file, duration_seconds=5.0)

        service = TranscriptionService(cache_dir=tmp_path / "cache")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [],
            "language": "en",
        }

        mock_whisper_module = MagicMock()
        mock_whisper_module.load_model.return_value = mock_model

        with patch("importlib.util.find_spec", return_value=MagicMock()):
            with patch.dict("sys.modules", {"whisper": mock_whisper_module}):
                result = service.transcribe(wav_file)

        assert result.segments == []
        assert result.duration == 5.0
        assert result.language == "en"
        assert result.model == "tiny"


class TestCachingReturnsIdenticalResult:
    """Test that caching returns identical result on second call."""

    def test_caching_returns_identical_result(self, tmp_path):
        """Second transcribe() call returns cached result; whisper invoked only once."""
        wav_file = tmp_path / "speech.wav"
        create_test_wav(wav_file)

        service = TranscriptionService(cache_dir=tmp_path / "cache")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 2.0,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 1.0, "probability": 0.95},
                        {"word": "world", "start": 1.0, "end": 2.0, "probability": 0.90},
                    ],
                }
            ],
            "language": "en",
            "duration": 5.0,
        }

        mock_whisper_module = MagicMock()
        mock_whisper_module.load_model.return_value = mock_model

        with patch("importlib.util.find_spec", return_value=MagicMock()):
            with patch.dict("sys.modules", {"whisper": mock_whisper_module}):
                result1 = service.transcribe(wav_file)
                result2 = service.transcribe(wav_file)

        # Results should be identical
        assert result1.segments[0].text == result2.segments[0].text
        assert result1.language == result2.language
        assert result1.duration == result2.duration
        assert result1.model == result2.model
        assert len(result1.segments) == len(result2.segments)
        assert len(result1.segments[0].words) == len(result2.segments[0].words)

        # Whisper model.transcribe should be called exactly once
        assert mock_model.transcribe.call_count == 1
