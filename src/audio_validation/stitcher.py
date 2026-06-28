"""Audio segment stitching utility for combining multiple transcription chunks.

Merges segments from multiple TranscriptionResult chunks into a single result,
deduplicating words in overlap regions and ensuring chronological order.
"""

from audio_validation.models import Segment, TranscriptionResult, WordTimestamp


def stitch_segments(
    chunks: list[TranscriptionResult], overlap_seconds: float = 5.0
) -> TranscriptionResult:
    """Stitch together multiple transcription chunks into a single result.

    Merges segments from all chunks, deduplicates words that appear in
    overlap regions (preferring higher confidence), and ensures the result
    is in strictly chronological order.

    Args:
        chunks: List of transcription results to stitch together.
        overlap_seconds: Duration of overlap between consecutive chunks in seconds.

    Returns:
        A single TranscriptionResult with all segments merged and deduplicated.
    """
    if not chunks:
        return TranscriptionResult(segments=[], language="", duration=0.0, model="")

    if len(chunks) == 1:
        return chunks[0]

    # Phase 1: Collect all words with their segment context, resolving duplicates
    # in overlap regions by keeping the higher-confidence version.
    # We work at the word level across all chunks to handle overlaps cleanly.

    # Build a global word map keyed by (rounded start time, word text).
    # For each key, keep the word with the highest confidence.
    global_words: dict[tuple[float, str], WordTimestamp] = {}

    for chunk_idx, chunk in enumerate(chunks):
        for seg in chunk.segments:
            for word in seg.words:
                key = (round(word.start, 3), word.word)
                if key not in global_words or word.confidence > global_words[key].confidence:
                    global_words[key] = word

    # Phase 2: Collect all segments, filtering out duplicate words.
    # Each segment keeps only words that are the "winner" in global_words.
    merged_segments: list[Segment] = []

    # Track which word keys have been emitted to avoid duplicates across segments
    emitted_words: set[tuple[float, str]] = set()

    for chunk in chunks:
        for seg in chunk.segments:
            deduped_words: list[WordTimestamp] = []
            for word in seg.words:
                key = (round(word.start, 3), word.word)
                if key in emitted_words:
                    # Already emitted by a previous segment
                    continue
                # Only keep the word if this instance is the winning version
                if global_words.get(key) is word or (
                    global_words.get(key) is not None
                    and word.confidence >= global_words[key].confidence
                    and word.start == global_words[key].start
                    and word.word == global_words[key].word
                ):
                    deduped_words.append(word)
                    emitted_words.add(key)

            # Only add the segment if it has words or non-empty text
            if deduped_words or seg.text:
                merged_segments.append(
                    Segment(
                        text=seg.text,
                        start=seg.start,
                        end=seg.end,
                        words=deduped_words,
                    )
                )

    # Phase 3: Sort by start time to ensure chronological order
    merged_segments.sort(key=lambda s: s.start)

    # Phase 4: Enforce strictly chronological order
    # Each segment.start must be >= previous segment.end
    for i in range(1, len(merged_segments)):
        prev = merged_segments[i - 1]
        curr = merged_segments[i]
        if curr.start < prev.end:
            new_start = prev.end
            new_end = max(curr.end, new_start + 0.01)
            merged_segments[i] = Segment(
                text=curr.text,
                start=new_start,
                end=new_end,
                words=curr.words,
            )

    # Calculate total duration as max segment end time
    total_duration = (
        max(seg.end for seg in merged_segments) if merged_segments else 0.0
    )

    return TranscriptionResult(
        segments=merged_segments,
        language=chunks[0].language,
        duration=total_duration,
        model=chunks[0].model,
    )
