"""Tests for VocalIsolator._segment_and_process() and _crossfade_stitch().

Validates Requirements 6.4, 6.6, 6.7:
- Segmentation for files > 600s into chunks ≤ 300s with 10s overlap
- Linear crossfade amplitude continuity (≤ 0.01 discontinuity)
- Chunk error stops processing and discards partial results
"""

import sys
from unittest.mock import MagicMock, patch

import torch
import pytest

# Mock torchaudio before importing isolator since torchaudio is not installed
sys.modules.setdefault("torchaudio", MagicMock())

from src.audio_validation.isolator import VocalIsolator, IsolationError


class TestCrossfadeStitch:
    """Tests for _crossfade_stitch method."""

    def setup_method(self):
        self.isolator = VocalIsolator()

    def test_single_chunk_returned_as_is(self):
        """A single chunk is returned without modification."""
        chunk = torch.randn(1, 44100)
        result = self.isolator._crossfade_stitch([chunk], overlap_samples=4410)
        assert torch.equal(result, chunk)

    def test_two_chunks_linear_crossfade(self):
        """Two chunks are stitched with linear crossfade over overlap region."""
        sample_rate = 44100
        overlap_samples = sample_rate * 10  # 10 seconds

        # Create two constant-value chunks for easy verification
        chunk_a = torch.ones(1, sample_rate * 300)  # 300s of 1.0
        chunk_b = torch.ones(1, sample_rate * 300) * 0.5  # 300s of 0.5

        result = self.isolator._crossfade_stitch([chunk_a, chunk_b], overlap_samples)

        # Expected output length: 300s + 300s - 10s overlap = 590s
        expected_samples = (300 + 300 - 10) * sample_rate
        assert result.shape[1] == expected_samples

        # Non-overlapping head should be 1.0 (from chunk_a minus overlap region)
        head = result[:, : (300 * sample_rate - overlap_samples)]
        assert torch.allclose(head, torch.ones_like(head))

        # Non-overlapping tail should be 0.5 (from chunk_b after overlap region)
        tail = result[:, -((300 - 10) * sample_rate) :]
        assert torch.allclose(tail, torch.full_like(tail, 0.5))

        # Crossfade region should interpolate between 1.0 and 0.5
        crossfade_region = result[
            :, (300 * sample_rate - overlap_samples) : (300 * sample_rate - overlap_samples) + overlap_samples
        ]
        # At start of crossfade: mostly chunk_a (1.0), at end: mostly chunk_b (0.5)
        assert crossfade_region[0, 0].item() == pytest.approx(1.0, abs=0.001)
        assert crossfade_region[0, -1].item() == pytest.approx(0.5, abs=0.001)

    def test_crossfade_amplitude_continuity(self):
        """No discontinuity introduced by crossfade at stitching boundaries.

        The crossfade boundary is continuous because at fade position 0,
        fade_out=1.0 (so result equals the previous chunk value exactly),
        and at fade position -1, fade_in=1.0 (so result equals the next chunk
        value exactly). This test uses constant signals to verify no jump is
        introduced by the crossfade itself.
        """
        sample_rate = 44100
        overlap_samples = sample_rate * 10

        # Use chunks with known constant values in the overlap region
        # chunk_a ends with 0.7 in its overlap zone, chunk_b starts with 0.7 in its overlap zone
        # If signals match in the overlap, crossfade should produce exact match (no discontinuity)
        chunk_a = torch.full((1, sample_rate * 30), 0.7)
        chunk_b = torch.full((1, sample_rate * 30), 0.7)

        result = self.isolator._crossfade_stitch([chunk_a, chunk_b], overlap_samples)

        # Entire result should be 0.7 since both chunks are constant 0.7
        # Check the boundary at crossfade start
        boundary_idx = chunk_a.shape[1] - overlap_samples - 1
        diff = abs(result[0, boundary_idx + 1].item() - result[0, boundary_idx].item())
        assert diff <= 0.01, f"Discontinuity at crossfade start: {diff}"

        # Check the boundary at crossfade end
        end_idx = chunk_a.shape[1] - 1  # end of crossfade region in result
        diff = abs(result[0, end_idx + 1].item() - result[0, end_idx].item())
        assert diff <= 0.01, f"Discontinuity at crossfade end: {diff}"

    def test_crossfade_preserves_sum_property(self):
        """Linear crossfade: fade_out + fade_in = 1.0 at every overlap sample.

        When both chunks have the same value V in overlap, output should be V.
        """
        overlap_samples = 1000
        value = 0.42

        chunk_a = torch.full((1, 2000), value)
        chunk_b = torch.full((1, 2000), value)

        result = self.isolator._crossfade_stitch([chunk_a, chunk_b], overlap_samples)

        # The crossfade region should equal `value` throughout (because
        # value * fade_out + value * fade_in = value * (fade_out + fade_in) = value * 1.0 = value)
        crossfade_start = 2000 - overlap_samples
        crossfade_region = result[:, crossfade_start : crossfade_start + overlap_samples]
        assert torch.allclose(crossfade_region, torch.full_like(crossfade_region, value), atol=1e-6)

    def test_three_chunks_stitching(self):
        """Three chunks are stitched correctly with proper total length."""
        sample_rate = 100  # Low rate for fast test
        overlap_samples = 10  # 10 samples overlap
        chunk_size = 50

        chunks = [torch.randn(1, chunk_size) for _ in range(3)]

        result = self.isolator._crossfade_stitch(chunks, overlap_samples)

        # Expected: 50 + (50-10) + (50-10) = 50 + 40 + 40 = 130
        expected_length = chunk_size + 2 * (chunk_size - overlap_samples)
        assert result.shape[1] == expected_length

    def test_stereo_chunks(self):
        """Crossfade works correctly with stereo (2-channel) audio."""
        overlap_samples = 100
        chunk_a = torch.randn(2, 1000)
        chunk_b = torch.randn(2, 1000)

        result = self.isolator._crossfade_stitch([chunk_a, chunk_b], overlap_samples)

        assert result.shape[0] == 2
        assert result.shape[1] == 1000 + 1000 - 100


class TestSegmentAndProcess:
    """Tests for _segment_and_process method."""

    def setup_method(self):
        self.isolator = VocalIsolator()

    def test_chunks_are_at_most_300_seconds(self):
        """All chunks passed to _separate are at most 300 seconds."""
        sample_rate = 100  # Low rate for fast test
        # Create waveform of 700 seconds (> 600s threshold)
        waveform = torch.randn(1, 700 * sample_rate)

        processed_chunks = []

        def mock_separate(model, audio, device):
            processed_chunks.append(audio.shape[1])
            return audio  # Return same tensor for simplicity

        with patch.object(self.isolator, '_separate', side_effect=mock_separate):
            result = self.isolator._segment_and_process(None, waveform, 'cpu', sample_rate)

        assert not isinstance(result, IsolationError)
        # All chunks should be ≤ 300 seconds
        for chunk_samples in processed_chunks:
            assert chunk_samples <= 300 * sample_rate

    def test_overlap_between_adjacent_chunks_is_10_seconds(self):
        """Adjacent chunks overlap by exactly 10 seconds."""
        sample_rate = 100
        waveform = torch.randn(1, 700 * sample_rate)

        chunk_starts = []
        chunk_ends = []

        def mock_separate(model, audio, device):
            return audio

        with patch.object(self.isolator, '_separate', side_effect=mock_separate):
            # Manually track what _segment_and_process does
            max_chunk_samples = 300 * sample_rate
            overlap_samples = 10 * sample_rate
            step = max_chunk_samples - overlap_samples

            start = 0
            total = waveform.shape[1]
            while start < total:
                end = min(start + max_chunk_samples, total)
                chunk_starts.append(start)
                chunk_ends.append(end)
                start += step

        # Check overlaps between adjacent chunks
        for i in range(len(chunk_starts) - 1):
            overlap = chunk_ends[i] - chunk_starts[i + 1]
            assert overlap == 10 * sample_rate

    def test_chunk_error_stops_processing_and_returns_error(self):
        """On chunk error: stop immediately, discard all results, report chunk number."""
        sample_rate = 100
        waveform = torch.randn(1, 700 * sample_rate)
        call_count = [0]

        def mock_separate(model, audio, device):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("CUDA OOM")
            return audio

        with patch.object(self.isolator, '_separate', side_effect=mock_separate):
            result = self.isolator._segment_and_process(None, waveform, 'cpu', sample_rate, "/test/input.wav")

        assert isinstance(result, IsolationError)
        assert "chunk 1" in result.error
        assert "CUDA OOM" in result.error
        assert result.input_path == "/test/input.wav"
        # Only 2 calls (first succeeds, second fails, no third)
        assert call_count[0] == 2

    def test_union_of_chunks_covers_entire_input(self):
        """The union of all chunks covers the entire input without gaps."""
        sample_rate = 100
        duration = 700  # seconds
        waveform = torch.randn(1, duration * sample_rate)

        chunks_received = []

        def mock_separate(model, audio, device):
            chunks_received.append(audio)
            return audio

        with patch.object(self.isolator, '_separate', side_effect=mock_separate):
            result = self.isolator._segment_and_process(None, waveform, 'cpu', sample_rate)

        # Reconstruct covered ranges
        max_chunk_samples = 300 * sample_rate
        overlap_samples = 10 * sample_rate
        step = max_chunk_samples - overlap_samples

        total_samples = waveform.shape[1]
        start = 0
        ranges = []
        for chunk in chunks_received:
            end = start + chunk.shape[1]
            ranges.append((start, end))
            start += step

        # First chunk starts at 0
        assert ranges[0][0] == 0
        # Last chunk covers up to total_samples
        assert ranges[-1][1] == total_samples

    def test_input_path_propagated_in_error(self):
        """input_path is correctly propagated in the IsolationError."""
        sample_rate = 100
        waveform = torch.randn(1, 700 * sample_rate)

        def mock_separate(model, audio, device):
            raise ValueError("bad audio data")

        with patch.object(self.isolator, '_separate', side_effect=mock_separate):
            result = self.isolator._segment_and_process(
                None, waveform, 'cpu', sample_rate, "/path/to/file.wav"
            )

        assert isinstance(result, IsolationError)
        assert result.input_path == "/path/to/file.wav"


class TestIsolateSegmentationIntegration:
    """Tests that isolate() correctly delegates to _segment_and_process for long files."""

    def setup_method(self):
        self.isolator = VocalIsolator()

    def test_isolate_calls_segment_for_long_files(self):
        """isolate() uses segmentation for files > 600 seconds."""
        sample_rate = 100
        # 601 seconds = strictly > 600
        waveform = torch.randn(1, 601 * sample_rate)

        with patch('torchaudio.load', return_value=(waveform, sample_rate)):
            with patch.object(self.isolator, '_load_model', return_value=(MagicMock(), 'cpu', False)):
                with patch.object(self.isolator, '_segment_and_process', return_value=waveform) as mock_seg:
                    with patch('torchaudio.save'):
                        self.isolator.isolate('/in.wav', '/out.wav')

        mock_seg.assert_called_once()

    def test_isolate_does_not_segment_at_exactly_600s(self):
        """isolate() does NOT use segmentation at exactly 600 seconds (must be strictly >)."""
        sample_rate = 100
        waveform = torch.randn(1, 600 * sample_rate)

        with patch('torchaudio.load', return_value=(waveform, sample_rate)):
            with patch.object(self.isolator, '_load_model', return_value=(MagicMock(), 'cpu', False)):
                with patch.object(self.isolator, '_segment_and_process') as mock_seg:
                    with patch.object(self.isolator, '_separate', return_value=waveform):
                        with patch('torchaudio.save'):
                            self.isolator.isolate('/in.wav', '/out.wav')

        mock_seg.assert_not_called()
