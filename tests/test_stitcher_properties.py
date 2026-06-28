"""Property tests for segment stitching chronological order and no duplication.

Feature: e2e-audio-validation, Property 15: Segment stitching chronological order and no duplication
**Validates: Requirements 7.4**
"""

from hypothesis import given, settings, assume
from hypothesis.strategies import integers, floats, composite, text, lists
from audio_validation.stitcher import stitch_segments
from audio_validation.models import Segment, TranscriptionResult, WordTimestamp


@composite
def overlapping_chunks_strategy(draw):
    """Generate 2-5 transcription chunks with overlapping time ranges.

    Each chunk is 10-30s long. Consecutive chunks overlap by 5s.
    Words in the overlap region appear in both adjacent chunks with
    varying confidence to exercise deduplication logic.
    """
    num_chunks = draw(integers(min_value=2, max_value=5))
    chunk_duration = draw(floats(min_value=10.0, max_value=30.0))
    overlap = 5.0

    chunks: list[TranscriptionResult] = []
    chunk_start = 0.0

    for chunk_idx in range(num_chunks):
        # Build 1-3 segments per chunk, spanning the chunk duration
        num_segments = draw(integers(min_value=1, max_value=3))
        seg_length = chunk_duration / num_segments

        segments: list[Segment] = []
        for seg_idx in range(num_segments):
            seg_start = chunk_start + seg_idx * seg_length
            seg_end = seg_start + seg_length

            # 1-5 words per segment, evenly spaced
            num_words = draw(integers(min_value=1, max_value=5))
            word_length = seg_length / num_words
            words: list[WordTimestamp] = []

            for w_idx in range(num_words):
                w_start = round(seg_start + w_idx * word_length, 3)
                w_end = round(w_start + word_length * 0.8, 3)
                confidence = draw(floats(min_value=0.5, max_value=1.0))
                word_text = f"w{chunk_idx}s{seg_idx}n{w_idx}"

                words.append(WordTimestamp(
                    word=word_text,
                    start=w_start,
                    end=w_end,
                    confidence=confidence,
                ))

            segments.append(Segment(
                text=" ".join(w.word for w in words),
                start=round(seg_start, 3),
                end=round(seg_end, 3),
                words=words,
            ))

        # Inject overlapping words: copy some words from the previous chunk's
        # overlap region into this chunk's first segment with different confidence.
        if chunk_idx > 0 and chunks:
            prev_chunk = chunks[-1]
            overlap_start = chunk_start  # this chunk starts in previous chunk's tail

            # Gather words from previous chunk that fall in the overlap zone
            overlap_words: list[WordTimestamp] = []
            for prev_seg in prev_chunk.segments:
                for pw in prev_seg.words:
                    if pw.start >= overlap_start - overlap:
                        overlap_words.append(pw)

            # Add up to 3 duplicates into the first segment of this chunk
            first_seg = segments[0]
            added_words = list(first_seg.words)
            for ow in overlap_words[:3]:
                dup_confidence = draw(floats(min_value=0.1, max_value=0.9))
                added_words.append(WordTimestamp(
                    word=ow.word,
                    start=ow.start,
                    end=ow.end,
                    confidence=dup_confidence,
                ))

            segments[0] = Segment(
                text=first_seg.text,
                start=first_seg.start,
                end=first_seg.end,
                words=added_words,
            )

        chunks.append(TranscriptionResult(
            segments=segments,
            language="en",
            duration=chunk_duration,
            model="tiny",
        ))

        # Next chunk starts overlap seconds before the current chunk ends
        chunk_start += chunk_duration - overlap

    return chunks


@given(overlapping_chunks_strategy())
@settings(max_examples=100)
def test_segment_stitching_properties(chunks):
    """Stitched segments maintain chronological order with no gaps or duplicates.

    **Validates: Requirements 7.4**

    Asserts:
    1. Segments sorted by start time (each segment.start >= previous segment.end)
    2. No gap >5s between consecutive segment.end and next segment.start
    3. No duplicate words (same rounded start time + same word text appearing twice)
    """
    result = stitch_segments(chunks, overlap_seconds=5.0)
    segments = result.segments

    # (1) Chronological order: each segment.start >= previous segment.end
    for i in range(1, len(segments)):
        prev = segments[i - 1]
        curr = segments[i]
        assert curr.start >= prev.end, (
            f"Not chronological: segment[{i-1}].end={prev.end} > "
            f"segment[{i}].start={curr.start}"
        )

    # (2) No gap >5s between consecutive segments
    for i in range(1, len(segments)):
        prev = segments[i - 1]
        curr = segments[i]
        gap = curr.start - prev.end
        assert gap <= 5.0, (
            f"Gap exceeds 5s: segment[{i-1}].end={prev.end}, "
            f"segment[{i}].start={curr.start}, gap={gap:.3f}s"
        )

    # (3) No duplicate words (same start time rounded to 3dp + same text)
    seen_words: set[tuple[float, str]] = set()
    for seg in segments:
        for word in seg.words:
            key = (round(word.start, 3), word.word)
            assert key not in seen_words, (
                f"Duplicate word: '{word.word}' at t={word.start}"
            )
            seen_words.add(key)
