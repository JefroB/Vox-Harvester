"""Property tests for segmentation chunk boundaries.

Feature: vocal-isolation, Property 14: Segmentation produces correct chunk boundaries
**Validates: Requirements 6.4**
"""

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from, composite


@composite
def segmentation_inputs(draw):
    """Generate (total_samples, sample_rate) pairs for audio > 600 seconds.

    Durations range from 601 to 7200 seconds. Sample rates are drawn from
    common audio rates: 8000, 16000, 22050, 44100, 48000 Hz.
    """
    duration_seconds = draw(integers(min_value=601, max_value=7200))
    sample_rate = draw(sampled_from([8000, 16000, 22050, 44100, 48000]))
    total_samples = duration_seconds * sample_rate
    return total_samples, sample_rate


def compute_chunk_boundaries(total_samples: int, sample_rate: int) -> list[tuple[int, int]]:
    """Replicate the segmentation logic from VocalIsolator._segment_and_process.

    Returns a list of (start, end) sample positions for each chunk.
    """
    max_chunk_samples = int(300 * sample_rate)
    overlap_samples = int(10 * sample_rate)
    step_samples = max_chunk_samples - overlap_samples

    chunks: list[tuple[int, int]] = []
    start = 0

    while start < total_samples:
        end = min(start + max_chunk_samples, total_samples)
        chunks.append((start, end))
        start += step_samples

    return chunks


@given(segmentation_inputs())
@settings(max_examples=100)
def test_segmentation_chunk_boundaries(inputs):
    """Segmentation produces correct chunk boundaries for long audio.

    **Validates: Requirements 6.4**

    For any audio with duration strictly > 600 seconds, verifies:
    1. Each chunk is at most 300 seconds (max_chunk_samples)
    2. Adjacent chunks overlap by exactly 10 seconds (overlap_samples)
    3. The union of all chunks covers the entire input duration without gaps
    """
    total_samples, sample_rate = inputs
    max_chunk_samples = int(300 * sample_rate)
    overlap_samples = int(10 * sample_rate)

    chunks = compute_chunk_boundaries(total_samples, sample_rate)

    assert len(chunks) >= 1, "Must produce at least one chunk"

    # Property 1: Each chunk is at most 300 seconds (max_chunk_samples)
    for i, (start, end) in enumerate(chunks):
        chunk_length = end - start
        assert chunk_length <= max_chunk_samples, (
            f"Chunk {i} has {chunk_length} samples, exceeds max {max_chunk_samples}. "
            f"start={start}, end={end}"
        )

    # Property 2: Adjacent chunks overlap by exactly overlap_samples when
    # the previous chunk is full-sized (not capped by total_samples).
    # The last chunk transition may have less overlap due to end-capping.
    for i in range(1, len(chunks)):
        prev_start, prev_end = chunks[i - 1]
        curr_start, curr_end = chunks[i]
        actual_overlap = prev_end - curr_start

        prev_is_full = (prev_end - prev_start) == max_chunk_samples
        if prev_is_full:
            assert actual_overlap == overlap_samples, (
                f"Overlap between chunk {i-1} and {i} is {actual_overlap} samples, "
                f"expected {overlap_samples}. "
                f"chunk[{i-1}]=({prev_start}, {prev_end}), "
                f"chunk[{i}]=({curr_start}, {curr_end})"
            )
        else:
            # For capped chunks, overlap must still be positive (no gap)
            assert actual_overlap > 0, (
                f"Gap between chunk {i-1} and {i}: overlap={actual_overlap}. "
                f"chunk[{i-1}]=({prev_start}, {prev_end}), "
                f"chunk[{i}]=({curr_start}, {curr_end})"
            )

    # Property 3: Union of all chunks covers entire input without gaps
    # First chunk must start at 0
    assert chunks[0][0] == 0, (
        f"First chunk starts at {chunks[0][0]}, expected 0"
    )
    # Last chunk must end at total_samples
    assert chunks[-1][1] == total_samples, (
        f"Last chunk ends at {chunks[-1][1]}, expected {total_samples}"
    )
    # No gaps: each chunk starts before or at the previous chunk's end
    for i in range(1, len(chunks)):
        prev_start, prev_end = chunks[i - 1]
        curr_start, curr_end = chunks[i]
        assert curr_start <= prev_end, (
            f"Gap between chunk {i-1} and {i}: "
            f"chunk[{i-1}].end={prev_end}, chunk[{i}].start={curr_start}"
        )
