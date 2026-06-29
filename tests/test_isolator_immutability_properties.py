"""Property test for original file immutability during vocal isolation.

**Validates: Requirements 2.4**

Property 6: Original file immutability
For any isolation job (successful or failed), the original Harvested_Sample
file SHALL have identical content (byte-for-byte) before and after processing.

The key invariant: torchaudio.load() only reads the file. The original file
is NEVER opened for writing by the isolation service.
"""

import hashlib
import importlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings
import pytest


# Pre-mock heavy dependencies so importing isolator.py doesn't trigger
# the audio_validation __init__.py chain (nltk → scipy → crash).
# We mock at sys.modules level BEFORE any import of the package.
_mock_torch = MagicMock()
_mock_torch.cuda.is_available.return_value = False
_mock_torch.cuda.OutOfMemoryError = type("OutOfMemoryError", (RuntimeError,), {})
_mock_torch.cuda.empty_cache = MagicMock()

_mock_torchaudio = MagicMock()
_mock_demucs = MagicMock()
_mock_demucs_pretrained = MagicMock()
_mock_demucs_apply = MagicMock()

# Inject mocks into sys.modules so imports inside isolator.py resolve to our mocks
sys.modules.setdefault("torch", _mock_torch)
sys.modules.setdefault("torchaudio", _mock_torchaudio)
sys.modules.setdefault("demucs", _mock_demucs)
sys.modules.setdefault("demucs.pretrained", _mock_demucs_pretrained)
sys.modules.setdefault("demucs.apply", _mock_demucs_apply)

# Also pre-mock the heavy __init__.py dependencies to prevent the import chain
sys.modules.setdefault("nltk", MagicMock())
sys.modules.setdefault("nltk.stem", MagicMock())
sys.modules.setdefault("scipy", MagicMock())
sys.modules.setdefault("whisper", MagicMock())

from src.audio_validation.isolator import VocalIsolator


@given(file_content=st.binary(min_size=44, max_size=4096))
@settings(max_examples=100)
def test_original_file_immutable_on_success(file_content, tmp_path_factory):
    """Original file content is unchanged after a successful isolation.

    **Validates: Requirements 2.4**
    """
    tmp_path = tmp_path_factory.mktemp("immutability_success")
    input_file = tmp_path / "sample.wav"
    output_file = tmp_path / "sample_isolated.wav"

    # Write generated content as the input file
    input_file.write_bytes(file_content)

    # Hash before processing
    hash_before = hashlib.sha256(input_file.read_bytes()).hexdigest()

    # Create fake torch tensor that behaves enough for the isolator
    fake_waveform = MagicMock()
    fake_waveform.shape = (1, 44100)  # 1 channel, 1 second at 44.1kHz
    fake_waveform.__getitem__ = MagicMock(return_value=fake_waveform)
    fake_waveform.to = MagicMock(return_value=fake_waveform)
    fake_waveform.cpu = MagicMock(return_value=fake_waveform)
    fake_waveform.mean = MagicMock(return_value=fake_waveform)
    fake_waveform.repeat = MagicMock(return_value=fake_waveform)

    fake_sources = MagicMock()
    fake_sources.__getitem__ = MagicMock(return_value=fake_waveform)

    fake_model = MagicMock()
    fake_model.to = MagicMock(return_value=fake_model)
    fake_model.eval = MagicMock(return_value=fake_model)

    # Configure mocks for this test run
    _mock_torch.cuda.is_available.return_value = False
    _mock_torchaudio.load.return_value = (fake_waveform, 44100)
    _mock_torchaudio.save = MagicMock()
    _mock_demucs_pretrained.get_model.return_value = fake_model
    _mock_demucs_apply.apply_model.return_value = fake_sources

    isolator = VocalIsolator()
    result = isolator.isolate(str(input_file), str(output_file))

    # Hash after processing
    hash_after = hashlib.sha256(input_file.read_bytes()).hexdigest()

    assert hash_before == hash_after, (
        f"Original file was modified during successful isolation. "
        f"Before: {hash_before}, After: {hash_after}"
    )


@given(file_content=st.binary(min_size=44, max_size=4096))
@settings(max_examples=100)
def test_original_file_immutable_on_failure(file_content, tmp_path_factory):
    """Original file content is unchanged after a failed isolation.

    **Validates: Requirements 2.4**
    """
    tmp_path = tmp_path_factory.mktemp("immutability_failure")
    input_file = tmp_path / "sample.wav"
    output_file = tmp_path / "sample_isolated.wav"

    # Write generated content as the input file
    input_file.write_bytes(file_content)

    # Hash before processing
    hash_before = hashlib.sha256(input_file.read_bytes()).hexdigest()

    # Create a mock waveform that will be loaded
    fake_waveform = MagicMock()
    fake_waveform.shape = (1, 44100)
    fake_waveform.__getitem__ = MagicMock(return_value=fake_waveform)
    fake_waveform.to = MagicMock(return_value=fake_waveform)

    fake_model = MagicMock()
    fake_model.to = MagicMock(return_value=fake_model)
    fake_model.eval = MagicMock(return_value=fake_model)

    # Configure mocks - make apply_model raise to simulate failure
    _mock_torch.cuda.is_available.return_value = False
    _mock_torchaudio.load.return_value = (fake_waveform, 44100)
    _mock_demucs_pretrained.get_model.return_value = fake_model
    _mock_demucs_apply.apply_model.side_effect = RuntimeError("Simulated Demucs failure")

    isolator = VocalIsolator()
    result = isolator.isolate(str(input_file), str(output_file))

    # Reset side_effect for next iteration
    _mock_demucs_apply.apply_model.side_effect = None

    # The isolator returns an IsolationError on failure, doesn't raise.
    # Regardless of outcome, the original file must be untouched.
    hash_after = hashlib.sha256(input_file.read_bytes()).hexdigest()

    assert hash_before == hash_after, (
        f"Original file was modified during failed isolation. "
        f"Before: {hash_before}, After: {hash_after}"
    )
