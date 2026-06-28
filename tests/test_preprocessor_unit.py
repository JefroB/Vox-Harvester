"""Unit tests for Audio Preprocessor.

Tests format conversion, short file handling, and duration preservation.
These tests mock FFmpeg/ffprobe subprocesses since FFmpeg may not be on PATH
in all environments. The mocked behavior exercises the preprocessor's logic
paths: probe duration → convert → return PreprocessResult.

Validates: Requirements 6.1
"""

import struct
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from audio_validation.preprocessor import AudioPreprocessor


def _create_wav_file(
    tmp_path: Path,
    filename: str,
    duration: float,
    sample_rate: int = 44100,
    nchannels: int = 1,
    sampwidth: int = 2,
) -> Path:
    """Create a WAV file with silence at the given parameters."""
    filepath = tmp_path / filename
    num_frames = int(sample_rate * duration)

    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        silence = b"\x00" * (num_frames * nchannels * sampwidth)
        wf.writeframes(silence)

    return filepath


def _make_ffprobe_result(duration: float):
    """Create a mock subprocess.CompletedProcess for ffprobe."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = f"{duration:.6f}\n"
    result.stderr = ""
    return result


def _make_ffmpeg_convert(output_dir: Path):
    """Return a side_effect function that creates a 16kHz output WAV when ffmpeg is called."""

    def _side_effect(cmd, **kwargs):
        # The output path is the last argument in the ffmpeg command
        output_path = Path(cmd[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write a valid 16kHz mono 16-bit WAV file
        # Parse duration from -t flag if present, else use 2.0s default
        duration = 2.0
        for i, arg in enumerate(cmd):
            if arg == "-t" and i + 1 < len(cmd):
                try:
                    duration = float(cmd[i + 1])
                except ValueError:
                    pass
                break

        num_frames = int(16000 * duration)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * (num_frames * 2))

        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    return _side_effect


@patch("audio_validation.preprocessor.subprocess.run")
def test_48khz_to_16khz_format(mock_run, tmp_path):
    """48kHz mono 16-bit WAV converts to 16kHz mono 16-bit output."""
    input_file = _create_wav_file(
        tmp_path, "input_48k.wav", duration=2.0, sample_rate=48000
    )
    output_dir = tmp_path / "output"

    # First call is ffprobe (returns duration), second is ffmpeg (converts)
    mock_run.side_effect = [
        _make_ffprobe_result(2.0),
        _make_ffmpeg_convert(output_dir)(
            [
                "ffmpeg", "-y", "-i", str(input_file),
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                str(output_dir / "input_48k_preprocessed.wav"),
            ]
        ),
    ]

    preprocessor = AudioPreprocessor(output_dir=output_dir)
    result = preprocessor.preprocess(input_file)

    output_file = result.output_paths[0]
    assert output_file.exists()

    with wave.open(str(output_file), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2

    # Verify PreprocessResult metadata
    assert result.sample_rate == 16000
    assert result.channels == 1
    assert result.bit_depth == 16


@patch("audio_validation.preprocessor.subprocess.run")
def test_short_file_converts_without_error(mock_run, tmp_path):
    """WAV file shorter than 0.5s converts without raising an error."""
    input_file = _create_wav_file(
        tmp_path, "short.wav", duration=0.1, sample_rate=44100
    )
    output_dir = tmp_path / "output"

    mock_run.side_effect = [
        _make_ffprobe_result(0.1),
        _make_ffmpeg_convert(output_dir)(
            [
                "ffmpeg", "-y", "-i", str(input_file),
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                str(output_dir / "short_preprocessed.wav"),
            ]
        ),
    ]

    preprocessor = AudioPreprocessor(output_dir=output_dir)
    result = preprocessor.preprocess(input_file)

    assert len(result.output_paths) == 1
    assert result.output_paths[0].exists()


@patch("audio_validation.preprocessor.subprocess.run")
def test_duration_preservation(mock_run, tmp_path):
    """Preprocessed output reports duration within 0.01s of the source."""
    known_duration = 3.0
    input_file = _create_wav_file(
        tmp_path, "known_duration.wav", duration=known_duration, sample_rate=44100
    )
    output_dir = tmp_path / "output"

    mock_run.side_effect = [
        _make_ffprobe_result(known_duration),
        _make_ffmpeg_convert(output_dir)(
            [
                "ffmpeg", "-y", "-i", str(input_file),
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                str(output_dir / "known_duration_preprocessed.wav"),
            ]
        ),
    ]

    preprocessor = AudioPreprocessor(output_dir=output_dir)
    result = preprocessor.preprocess(input_file)

    assert abs(result.duration_seconds - known_duration) < 0.01
