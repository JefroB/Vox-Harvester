"""Property tests for source file preservation.

Feature: e2e-audio-validation, Property 3: Preprocessor preserves source file

Validates: Requirements 1.7
"""

import hashlib
import struct
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, settings
from hypothesis.strategies import floats, integers

from audio_validation.preprocessor import AudioPreprocessor


def _mock_ffprobe_success(duration: float):
    """Return a mock subprocess.run result simulating successful ffprobe."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = f"{duration:.6f}\n"
    result.stderr = ""
    return result


def _mock_ffmpeg_success(cmd, **kwargs):
    """Mock subprocess.run that simulates ffprobe (returning duration) and ffmpeg (creating output file)."""
    if "ffprobe" in cmd[0]:
        # Parse the source path from the command to get the actual duration
        source_path = Path(cmd[-1])
        with wave.open(str(source_path), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        result = MagicMock()
        result.returncode = 0
        result.stdout = f"{duration:.6f}\n"
        result.stderr = ""
        return result
    elif "ffmpeg" in cmd[0]:
        # Find the output path (last argument) and create a dummy output file
        output_path = Path(cmd[-1])
        # Create a minimal valid WAV file as output
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            # Write 1 second of silence as dummy output
            wf.writeframes(struct.pack("<16000h", *([0] * 16000)))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result
    raise ValueError(f"Unexpected command: {cmd}")


@given(
    sample_rate=integers(min_value=8000, max_value=48000),
    duration=floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_preprocessor_preserves_source_file(sample_rate, duration):
    """After preprocessing, the source file SHA-256 hash is unchanged.

    **Validates: Requirements 1.7**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Generate a valid WAV file at the given sample rate and duration
        source_path = tmp_path / "source.wav"
        num_frames = int(sample_rate * duration)
        with wave.open(str(source_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(struct.pack(f"<{num_frames}h", *([0] * num_frames)))

        # Compute SHA-256 hash of the source file before preprocessing
        with open(source_path, "rb") as f:
            original_hash = hashlib.sha256(f.read()).hexdigest()

        # Preprocess the audio file (mocking FFmpeg subprocess calls)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        preprocessor = AudioPreprocessor(output_dir=output_dir)

        with patch("audio_validation.preprocessor.subprocess.run", side_effect=_mock_ffmpeg_success):
            preprocessor.preprocess(source_path)

        # Compute SHA-256 hash of the source file after preprocessing
        with open(source_path, "rb") as f:
            postprocessed_hash = hashlib.sha256(f.read()).hexdigest()

        # Assert the hashes are identical (source file was not modified)
        assert original_hash == postprocessed_hash
