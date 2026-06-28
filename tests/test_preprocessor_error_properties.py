"""Property tests for preprocessor error on invalid input.

Feature: e2e-audio-validation, Property 4: Preprocessor error on invalid input.

Validates: Requirements 1.5, 1.6
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import characters

from audio_validation.errors import PreprocessError
from audio_validation.preprocessor import AudioPreprocessor


@given(
    file_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=characters(whitelist_categories=("L", "N")),
    )
)
@settings(max_examples=100)
def test_nonexistent_path_raises_error(file_name):
    """Property 4a: Non-existent paths raise PreprocessError with file_path.

    Validates: Requirements 1.5
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        preprocessor = AudioPreprocessor(output_dir=tmp_path)
        non_existent_path = tmp_path / file_name
        with pytest.raises(PreprocessError) as exc_info:
            preprocessor.preprocess(non_existent_path)
        assert exc_info.value.file_path == non_existent_path


@given(audio_bytes=st.binary(min_size=10, max_size=1000))
@settings(max_examples=100)
def test_invalid_audio_bytes_raises_error(audio_bytes):
    """Property 4b: Files with random non-audio bytes raise PreprocessError.

    Validates: Requirements 1.6
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        invalid_audio_path = tmp_path / "invalid_audio.wav"
        invalid_audio_path.write_bytes(audio_bytes)

        preprocessor = AudioPreprocessor(output_dir=tmp_path)
        with pytest.raises(PreprocessError) as exc_info:
            preprocessor.preprocess(invalid_audio_path)
        assert exc_info.value.file_path == invalid_audio_path
