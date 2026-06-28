"""Property tests for Audio Preprocessor format invariants.

Feature: e2e-audio-validation, Property 1: Preprocessor format invariant
"""

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import pytest
import hypothesis.strategies as st
from hypothesis import given, settings

from audio_validation.preprocessor import AudioPreprocessor


def _find_ffmpeg() -> str | None:
    """Locate ffmpeg on this system, checking common install locations."""
    # Check PATH first
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check known locations on this machine
    candidates = [
        Path(r"C:\Program Files\Shotcut\ffmpeg.exe"),
        Path(r"D:\Vox Harvester\node_modules\ffmpeg-static\ffmpeg.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            # Verify ffprobe sibling exists (preprocessor derives it from ffmpeg path)
            ffprobe = Path(str(candidate).replace("ffmpeg", "ffprobe"))
            if ffprobe.exists():
                return str(candidate)
    return None


FFMPEG_PATH = _find_ffmpeg()

pytestmark = pytest.mark.skipif(
    FFMPEG_PATH is None,
    reason="ffmpeg/ffprobe not found on this system",
)


def _create_wav(path: Path, sample_rate: int, channels: int, bit_depth: int, duration: float = 1.0) -> None:
    """Generate a valid WAV file with the specified format parameters."""
    n_frames = int(sample_rate * duration)
    sampwidth = bit_depth // 8

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        # Write silence (zero samples). For 8-bit WAV, silence is 128.
        if sampwidth == 1:
            wf.writeframes(bytes([128] * n_frames * channels))
        else:
            wf.writeframes(b"\x00" * n_frames * channels * sampwidth)


class TestPreprocessorFormatInvariant:
    """**Validates: Requirements 1.1, 1.2**

    For any valid audio file at any sample rate (8kHz-96kHz), any channel
    count, and any bit depth, the Audio Preprocessor SHALL produce output
    that is exactly 16kHz, mono, 16-bit PCM WAV.
    """

    @given(
        sample_rate=st.integers(min_value=8000, max_value=96000),
        channels=st.sampled_from([1, 2]),
        bit_depth=st.sampled_from([8, 16]),
    )
    @settings(max_examples=100, deadline=None)
    def test_output_is_always_16khz_mono_16bit(self, sample_rate: int, channels: int, bit_depth: int) -> None:
        """Preprocessor output is always exactly 16kHz, mono, 16-bit PCM WAV."""
        tmp_dir = tempfile.mkdtemp(prefix="pbt_preprocess_")
        try:
            tmp_path = Path(tmp_dir)

            # Arrange: create a WAV file with arbitrary format parameters
            input_file = tmp_path / "source.wav"
            _create_wav(input_file, sample_rate, channels, bit_depth)

            output_dir = tmp_path / "output"
            output_dir.mkdir()

            # Act: preprocess the file
            preprocessor = AudioPreprocessor(ffmpeg_path=FFMPEG_PATH, output_dir=output_dir)
            result = preprocessor.preprocess(input_file)

            # Assert: output format is always 16kHz, mono, 16-bit
            assert len(result.output_paths) >= 1, "Expected at least one output file"

            for output_path in result.output_paths:
                assert output_path.exists(), f"Output file does not exist: {output_path}"
                with wave.open(str(output_path), "rb") as wf:
                    assert wf.getframerate() == 16000, (
                        f"Expected 16kHz sample rate, got {wf.getframerate()} "
                        f"(input was {sample_rate}Hz)"
                    )
                    assert wf.getnchannels() == 1, (
                        f"Expected mono (1 channel), got {wf.getnchannels()} "
                        f"(input had {channels} channels)"
                    )
                    assert wf.getsampwidth() == 2, (
                        f"Expected 16-bit (sampwidth=2), got {wf.getsampwidth()} "
                        f"(input was {bit_depth}-bit)"
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
