"""Property tests for AudioPreprocessor chunking correctness.

Feature: e2e-audio-validation, Property 2: Preprocessor chunking correctness

Validates: Requirements 1.4
"""

import struct
import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from audio_validation.preprocessor import AudioPreprocessor


def _create_wav_file(path: Path, duration_seconds: float, sample_rate: int = 16000) -> None:
    """Create a minimal WAV file with the given duration (silence)."""
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        # Write silence in batches to avoid massive allocations
        batch_size = sample_rate * 10  # 10 seconds
        silent_batch = struct.pack(f"<{batch_size}h", *([0] * batch_size))
        remaining = num_frames
        while remaining > 0:
            write_count = min(remaining, batch_size)
            if write_count == batch_size:
                wf.writeframes(silent_batch)
            else:
                wf.writeframes(struct.pack(f"<{write_count}h", *([0] * write_count)))
            remaining -= write_count


def _mock_subprocess_for_chunking(duration: float):
    """Create a subprocess.run mock that simulates ffprobe + ffmpeg chunking.

    ffprobe returns the given duration.
    ffmpeg creates output WAV chunks with the correct duration based on -ss and -t args.
    """

    def _side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""

        if "ffprobe" in cmd[0]:
            result.stdout = f"{duration:.6f}\n"
            return result

        if "ffmpeg" in cmd[0]:
            # Parse -ss (start time) and -t (chunk duration) from the command
            ss_value = 0.0
            t_value = 300.0
            output_path = Path(cmd[-1])

            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    ss_value = float(cmd[i + 1])
                elif arg == "-t" and i + 1 < len(cmd):
                    t_value = float(cmd[i + 1])

            # Create a WAV file with the chunk duration
            chunk_frames = int(t_value * 16000)
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                # Write silence — batch for speed
                batch_size = 16000 * 10
                remaining = chunk_frames
                while remaining > 0:
                    write_count = min(remaining, batch_size)
                    wf.writeframes(b"\x00\x00" * write_count)
                    remaining -= write_count

            return result

        raise ValueError(f"Unexpected command: {cmd}")

    return _side_effect


@given(duration=st.floats(min_value=301.0, max_value=900.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=20, deadline=None)
def test_preprocessor_chunking_correctness(duration: float) -> None:
    """Property 2: Preprocessor chunking correctness.

    For audio files with duration >300s, verify:
    1. Each chunk duration ≤ 300s
    2. Consecutive chunks overlap by exactly 5s (chunk N+1 starts at chunk N start + 295s)
    3. Chunks are returned in chronological order
    4. Total coverage equals source duration within 0.1s tolerance

    **Validates: Requirements 1.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create a source WAV file (content doesn't matter, we mock FFmpeg)
        source_path = tmp_path / "source.wav"
        # Create a small dummy file — the mock handles the rest
        _create_wav_file(source_path, 1.0)

        # Set up output directory
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        preprocessor = AudioPreprocessor(output_dir=output_dir)

        # Run preprocess with mocked subprocess
        with patch(
            "audio_validation.preprocessor.subprocess.run",
            side_effect=_mock_subprocess_for_chunking(duration),
        ):
            result = preprocessor.preprocess(source_path)

        output_paths = result.output_paths

        # Must have more than 1 chunk for files > 300s
        assert len(output_paths) > 1, f"Expected multiple chunks for {duration:.1f}s file"

        # --- Assertion 1: Each chunk ≤ 300s ---
        chunk_durations: list[float] = []
        for i, chunk_path in enumerate(output_paths):
            with wave.open(str(chunk_path), "r") as wf:
                chunk_dur = wf.getnframes() / wf.getframerate()
            chunk_durations.append(chunk_dur)
            assert chunk_dur <= 300.0 + 0.01, (
                f"Chunk {i} exceeds 300s: {chunk_dur:.3f}s"
            )

        # --- Assertion 2: Consecutive chunks overlap by exactly 5s ---
        # The preprocessor uses step = 295s between chunk starts.
        # Overlap between chunk i-1 and chunk i = prev_duration - step.
        # For full (non-last) chunks of 300s, overlap = 300 - 295 = 5s.
        step = 295.0
        for i in range(1, len(output_paths)):
            prev_dur = chunk_durations[i - 1]
            # Only verify overlap for non-last transitions where prev chunk is full 300s
            if prev_dur >= 300.0 - 0.01:
                overlap = prev_dur - step
                assert abs(overlap - 5.0) < 0.1, (
                    f"Overlap between chunk {i-1} and {i} is {overlap:.3f}s, expected 5.0s"
                )

        # --- Assertion 3: Chunks in chronological order ---
        chunk_indices: list[int] = []
        for p in output_paths:
            stem = p.stem
            parts = stem.split("_chunk_")
            assert len(parts) == 2, f"Unexpected chunk filename format: {p.name}"
            chunk_indices.append(int(parts[1]))
        assert chunk_indices == sorted(chunk_indices), "Chunks not in chronological order"
        assert chunk_indices == list(range(len(output_paths))), (
            "Chunk indices not sequential starting from 0"
        )

        # --- Assertion 4: Total coverage equals source duration within 0.1s ---
        # Coverage = (N-1) * step + last_chunk_duration
        # This represents the span from time 0 to the end of the last chunk.
        n_chunks = len(output_paths)
        total_coverage = (n_chunks - 1) * step + chunk_durations[-1]
        assert abs(total_coverage - duration) < 0.1, (
            f"Total coverage {total_coverage:.3f}s != source duration {duration:.3f}s "
            f"(diff: {abs(total_coverage - duration):.4f}s)"
        )
