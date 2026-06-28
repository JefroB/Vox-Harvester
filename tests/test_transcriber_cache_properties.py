"""Property tests for transcription cache idempotence.

Feature: e2e-audio-validation, Property 6: Transcription cache idempotence

Validates: Requirements 2.6
"""

import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis.strategies import floats

from audio_validation.transcriber import TranscriptionService


def create_wav_file(file_path: Path, duration_seconds: float) -> None:
    """Create a valid 16kHz mono 16-bit WAV file with given duration."""
    sample_rate = 16000
    frames = int(duration_seconds * sample_rate)
    audio_data = bytes([0] * (frames * 2))  # 16-bit silence

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)


@given(duration=floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_transcription_cache_idempotence(duration: float) -> None:
    """Transcribing the same file twice returns identical results; Whisper invoked once.

    **Validates: Requirements 2.6**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        wav_file = tmp_path / "test.wav"
        create_wav_file(wav_file, duration)

        # Create a mock whisper module and inject it into sys.modules
        # so that `import whisper` inside the transcriber resolves correctly.
        mock_whisper = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "text": "test",
                    "start": 0.0,
                    "end": 1.0,
                    "words": [
                        {
                            "word": "test",
                            "start": 0.0,
                            "end": 1.0,
                            "probability": 0.9,
                        }
                    ],
                }
            ],
            "language": "en",
        }
        mock_whisper.load_model.return_value = mock_model

        # Patch sys.modules so `import whisper` works, and patch find_spec
        # so the dependency check passes.
        with patch.dict(sys.modules, {"whisper": mock_whisper}), \
             patch("importlib.util.find_spec", return_value=MagicMock()):

            cache_dir = tmp_path / "cache"
            service = TranscriptionService(cache_dir=cache_dir)

            # First transcription — should invoke Whisper
            result1 = service.transcribe(wav_file)

            # Second transcription — should serve from cache
            result2 = service.transcribe(wav_file)

            # Both results must be identical
            assert result1.segments == result2.segments
            assert result1.language == result2.language
            assert result1.duration == result2.duration
            assert result1.model == result2.model

            # Whisper model.transcribe called exactly once (cache served second call)
            assert mock_model.transcribe.call_count == 1