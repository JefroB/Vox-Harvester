"""Integration tests for the convenience validate_audio function.

Validates Requirements 7.1, 7.2: end-to-end pipeline produces correct
RelevanceResult for speech and silence fixtures.
"""

import shutil
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from audio_validation import RelevanceResult, validate_audio


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SPEECH_FIXTURE = FIXTURES_DIR / "speech_5s.wav"
SILENCE_FIXTURE = FIXTURES_DIR / "silence.wav"


def _make_subprocess_side_effect(source_fixture: Path):
    """Create a subprocess.run side_effect that handles ffprobe and ffmpeg calls.

    ffprobe calls return duration '5.0'.
    ffmpeg calls copy the source fixture to the output path so wave.open succeeds.
    """

    def side_effect(cmd, **kwargs):
        cmd_str = str(cmd[0])
        if "ffprobe" in cmd_str:
            return CompletedProcess(args=cmd, returncode=0, stdout="5.0\n", stderr="")
        # ffmpeg call — copy source to output path (last positional arg)
        output_path = Path(cmd[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(source_fixture), str(output_path))
        return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return side_effect


WHISPER_SPEECH_RESULT = {
    "segments": [
        {
            "text": "Hello world this is a test",
            "start": 0.0,
            "end": 2.5,
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.4, "probability": 0.95},
                {"word": "world", "start": 0.45, "end": 0.8, "probability": 0.92},
                {"word": "this", "start": 0.85, "end": 1.0, "probability": 0.90},
                {"word": "is", "start": 1.05, "end": 1.15, "probability": 0.88},
                {"word": "a", "start": 1.2, "end": 1.25, "probability": 0.85},
                {"word": "test", "start": 1.3, "end": 1.6, "probability": 0.93},
            ],
        }
    ],
    "language": "en",
    "duration": 5.0,
}

WHISPER_SILENCE_RESULT = {
    "segments": [],
    "language": "en",
    "duration": 5.0,
}


def _create_whisper_mock(transcribe_return_value):
    """Create a mock whisper module with a mock model."""
    mock_whisper = MagicMock()
    mock_whisper.__spec__ = MagicMock()  # satisfy importlib.util.find_spec
    mock_model = MagicMock()
    mock_model.transcribe.return_value = transcribe_return_value
    mock_whisper.load_model.return_value = mock_model
    return mock_whisper


@patch("subprocess.run")
def test_validate_audio_with_speech_fixture(mock_run):
    """End-to-end with speech fixture: returns RelevanceResult with score > 0.0."""
    mock_run.side_effect = _make_subprocess_side_effect(SPEECH_FIXTURE)
    mock_whisper = _create_whisper_mock(WHISPER_SPEECH_RESULT)

    with patch.dict(sys.modules, {"whisper": mock_whisper}):
        result = validate_audio(SPEECH_FIXTURE, search_term="hello world test")

    assert isinstance(result, RelevanceResult)
    assert result.score > 0.0
    assert result.is_relevant is True


@patch("subprocess.run")
def test_validate_audio_with_silence_fixture(mock_run):
    """End-to-end with silence fixture: returns score = 0.0."""
    mock_run.side_effect = _make_subprocess_side_effect(SILENCE_FIXTURE)
    mock_whisper = _create_whisper_mock(WHISPER_SILENCE_RESULT)

    with patch.dict(sys.modules, {"whisper": mock_whisper}):
        result = validate_audio(SILENCE_FIXTURE, search_term="hello world")

    assert isinstance(result, RelevanceResult)
    assert result.score == 0.0
    assert result.is_relevant is False
