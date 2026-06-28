"""Property tests for invalid WAV rejection without Whisper invocation.

Feature: e2e-audio-validation, Property 7: Invalid WAV rejection without Whisper invocation.
Validates: Requirements 2.7
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
import hypothesis.strategies as st

from audio_validation.errors import InvalidAudioError
from audio_validation.transcriber import TranscriptionService


@given(data=st.binary(min_size=1, max_size=1000))
@settings(max_examples=100)
def test_random_bytes_rejected(data):
    """Random bytes that aren't valid WAV must raise InvalidAudioError without invoking Whisper."""
    assume(not data.startswith(b"RIFF"))

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cache_dir = tmp_path / "cache"
        file_path = tmp_path / "test.wav"
        file_path.write_bytes(data)

        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            service = TranscriptionService(cache_dir=cache_dir)
            with pytest.raises(InvalidAudioError) as exc_info:
                service.transcribe(file_path)

            assert exc_info.value.file_path == file_path
            mock_whisper.load_model.assert_not_called()


@given(prefix=st.binary(min_size=4, max_size=4), body=st.binary(min_size=0, max_size=500))
@settings(max_examples=100)
def test_wrong_header_rejected(prefix, body):
    """Files with non-RIFF headers must raise InvalidAudioError without invoking Whisper."""
    assume(prefix != b"RIFF")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cache_dir = tmp_path / "cache"
        file_path = tmp_path / "test.wav"
        file_path.write_bytes(prefix + body)

        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            service = TranscriptionService(cache_dir=cache_dir)
            with pytest.raises(InvalidAudioError) as exc_info:
                service.transcribe(file_path)

            assert exc_info.value.file_path == file_path
            mock_whisper.load_model.assert_not_called()


def test_zero_length_file_rejected():
    """Zero-length files must raise InvalidAudioError without invoking Whisper."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cache_dir = tmp_path / "cache"
        file_path = tmp_path / "test.wav"
        file_path.write_bytes(b"")

        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            service = TranscriptionService(cache_dir=cache_dir)
            with pytest.raises(InvalidAudioError) as exc_info:
                service.transcribe(file_path)

            assert exc_info.value.file_path == file_path
            mock_whisper.load_model.assert_not_called()
