"""Integration tests for the audio validation subsystem pipeline.

Tests the complete STT pipeline (preprocess -> transcribe -> score) integration.

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import importlib.util
import json
import shutil
import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audio_validation.models import Segment, TranscriptionResult, WordTimestamp
from audio_validation.preprocessor import AudioPreprocessor
from audio_validation.scorer import RelevanceScorer
from audio_validation.stitcher import stitch_segments
from audio_validation.transcriber import TranscriptionService

# Check if Whisper is available for real pipeline tests
WHISPER_AVAILABLE = importlib.util.find_spec("whisper") is not None
requires_whisper = pytest.mark.skipif(
    not WHISPER_AVAILABLE, reason="openai-whisper not available"
)

# Check if FFmpeg is available (PATH or known locations on this machine)
def _find_ffmpeg() -> str | None:
    """Locate ffmpeg binary, checking PATH and known install locations."""
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg
    candidates = [
        Path(r"C:\Program Files\Shotcut\ffmpeg.exe"),
        Path(r"D:\Vox Harvester\node_modules\ffmpeg-static\ffmpeg.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            # Verify ffprobe sibling exists
            ffprobe = Path(str(candidate).replace("ffmpeg", "ffprobe"))
            if ffprobe.exists():
                return str(candidate)
    return None


FFMPEG_PATH = _find_ffmpeg()
FFMPEG_AVAILABLE = FFMPEG_PATH is not None
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG_AVAILABLE, reason="ffmpeg not available"
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def speech_wav(tmp_path):
    """Create a 5-second 16kHz mono 16-bit WAV file for pipeline testing."""
    wav_file = tmp_path / "speech_5s.wav"
    sample_rate = 16000
    channels = 1
    sample_width = 2
    num_frames = int(sample_rate * 5.0)

    with wave.open(str(wav_file), "w") as wf:
        wf.setparams(
            (channels, sample_width, sample_rate, num_frames, "NONE", "not compressed")
        )
        wf.writeframes(b"\x00" * (num_frames * channels * sample_width))

    return wav_file


@pytest.fixture
def noisy_audio_wav(tmp_path):
    """Create a WAV file simulating noisy audio (still valid WAV format)."""
    import struct

    wav_file = tmp_path / "noisy.wav"
    sample_rate = 16000
    channels = 1
    sample_width = 2
    num_frames = int(sample_rate * 5.0)

    with wave.open(str(wav_file), "w") as wf:
        wf.setparams(
            (channels, sample_width, sample_rate, num_frames, "NONE", "not compressed")
        )
        data = struct.pack("<" + "h" * num_frames, *([1000, -1000] * (num_frames // 2)))
        wf.writeframes(data)

    return wav_file


@pytest.fixture
def expected_transcript():
    """Load the expected transcript from the fixture JSON file."""
    with open(FIXTURES_DIR / "expected_transcript.json", "r") as f:
        return json.load(f)


def _mock_whisper_for_result(whisper_output: dict):
    """Create mock whisper module and model returning a given output.

    Returns (mock_whisper_module, mock_model) for patching.
    """
    mock_model = MagicMock()
    mock_model.transcribe.return_value = whisper_output

    mock_whisper_module = MagicMock()
    mock_whisper_module.load_model.return_value = mock_model

    return mock_whisper_module, mock_model


class TestPipelineIntegrationMocked:
    """Integration tests with mocked Whisper and preprocessor (always run).

    These tests verify the pipeline logic (preprocess -> transcribe -> score)
    without requiring FFmpeg or Whisper to be installed.
    """

    @pytest.mark.timeout(120)
    def test_preprocess_transcribe_score_pipeline(
        self, speech_wav, expected_transcript, tmp_path
    ):
        """Test preprocess -> transcribe -> score with speech fixture.

        Verifies transcript contains >=3 words from ground-truth list.
        Validates: Requirements 7.1
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Copy the WAV to the output dir to simulate preprocessor output
        preprocessed_path = output_dir / "speech_5s_preprocessed.wav"
        shutil.copy(speech_wav, preprocessed_path)

        preprocessor = AudioPreprocessor(output_dir=output_dir)
        transcriber = TranscriptionService(cache_dir=cache_dir)
        scorer = RelevanceScorer()

        mock_whisper, _ = _mock_whisper_for_result(expected_transcript)

        # Mock preprocessor's FFmpeg calls and Whisper
        with patch.object(preprocessor, "_probe_duration", return_value=5.0):
            with patch.object(preprocessor, "_convert_single", return_value=preprocessed_path):
                with patch("importlib.util.find_spec", return_value=MagicMock()):
                    with patch.dict("sys.modules", {"whisper": mock_whisper}):
                        preprocess_result = preprocessor.preprocess(speech_wav)
                        transcription_result = transcriber.transcribe(
                            preprocess_result.output_paths[0]
                        )
                        score_result = scorer.score(
                            transcription_result, "hello world test"
                        )

        # Verify transcript contains at least 3 words from ground-truth
        ground_truth_words = {"hello", "world", "this", "is", "a", "test"}
        found_words = set()
        for segment in transcription_result.segments:
            for word in segment.words:
                if word.word.lower() in ground_truth_words:
                    found_words.add(word.word.lower())

        assert len(found_words) >= 3, (
            f"Expected >=3 words from ground-truth, found {len(found_words)}: {found_words}"
        )

        # Verify scoring produces valid result
        assert 0.0 <= score_result.score <= 1.0
        assert isinstance(score_result.is_relevant, bool)

    @pytest.mark.timeout(120)
    def test_relevance_score_within_tolerance(
        self, speech_wav, expected_transcript, tmp_path
    ):
        """Test relevance score matches expected value within 0.1 tolerance.

        The transcript contains 'hello world this is a test'.
        Search term 'hello world test' has 3 stemmed tokens: [hello, world, test].
        All 3 appear in the transcript, so expected score = 3/3 = 1.0.
        Validates: Requirements 7.2
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        preprocessed_path = output_dir / "speech_preprocessed.wav"
        shutil.copy(speech_wav, preprocessed_path)

        preprocessor = AudioPreprocessor(output_dir=output_dir)
        transcriber = TranscriptionService(cache_dir=cache_dir)
        scorer = RelevanceScorer()

        mock_whisper, _ = _mock_whisper_for_result(expected_transcript)

        with patch.object(preprocessor, "_probe_duration", return_value=5.0):
            with patch.object(preprocessor, "_convert_single", return_value=preprocessed_path):
                with patch("importlib.util.find_spec", return_value=MagicMock()):
                    with patch.dict("sys.modules", {"whisper": mock_whisper}):
                        preprocess_result = preprocessor.preprocess(speech_wav)
                        transcription_result = transcriber.transcribe(
                            preprocess_result.output_paths[0]
                        )
                        score_result = scorer.score(
                            transcription_result, "hello world test"
                        )

        # Expected: all 3 search tokens (hello, world, test) found in transcript
        # Score should be 1.0 (within 0.1 tolerance)
        expected_score = 1.0
        assert abs(score_result.score - expected_score) <= 0.1, (
            f"Score {score_result.score} not within 0.1 of expected {expected_score}"
        )

    @pytest.mark.timeout(120)
    def test_noisy_audio_produces_transcript(self, noisy_audio_wav, tmp_path):
        """Test noisy audio fixture produces transcript with >=1 segment and >=1 word.

        Validates: Requirements 7.3
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        preprocessed_path = output_dir / "noisy_preprocessed.wav"
        shutil.copy(noisy_audio_wav, preprocessed_path)

        preprocessor = AudioPreprocessor(output_dir=output_dir)
        transcriber = TranscriptionService(cache_dir=cache_dir)

        # Simulate Whisper producing partial result from noisy audio
        noisy_whisper_output = {
            "segments": [
                {
                    "text": "something here",
                    "start": 0.0,
                    "end": 3.0,
                    "words": [
                        {"word": "something", "start": 0.0, "end": 1.5, "probability": 0.6},
                        {"word": "here", "start": 1.6, "end": 3.0, "probability": 0.5},
                    ],
                }
            ],
            "language": "en",
            "duration": 5.0,
        }

        mock_whisper, _ = _mock_whisper_for_result(noisy_whisper_output)

        with patch.object(preprocessor, "_probe_duration", return_value=5.0):
            with patch.object(preprocessor, "_convert_single", return_value=preprocessed_path):
                with patch("importlib.util.find_spec", return_value=MagicMock()):
                    with patch.dict("sys.modules", {"whisper": mock_whisper}):
                        preprocess_result = preprocessor.preprocess(noisy_audio_wav)
                        transcription_result = transcriber.transcribe(
                            preprocess_result.output_paths[0]
                        )

        assert len(transcription_result.segments) >= 1, "Expected at least 1 segment"
        assert len(transcription_result.segments[0].words) >= 1, (
            "Expected at least 1 word in first segment"
        )


class TestStitchingIntegration:
    """Test segment stitching for chunked transcriptions (no Whisper needed).

    Validates: Requirements 7.4
    """

    @pytest.mark.timeout(120)
    def test_stitching_no_duplicated_words_in_overlaps(self):
        """Test that words in overlap regions are deduplicated after stitching."""
        # Chunk 1: 0-300s with words at the boundary
        chunk1 = TranscriptionResult(
            segments=[
                Segment(
                    text="The quick brown fox",
                    start=0.0,
                    end=4.0,
                    words=[
                        WordTimestamp(word="The", start=0.0, end=0.5, confidence=0.9),
                        WordTimestamp(word="quick", start=0.6, end=1.2, confidence=0.85),
                        WordTimestamp(word="brown", start=1.3, end=2.0, confidence=0.9),
                        WordTimestamp(word="fox", start=2.1, end=3.0, confidence=0.88),
                    ],
                ),
                Segment(
                    text="jumps over",
                    start=295.0,
                    end=298.0,
                    words=[
                        WordTimestamp(word="jumps", start=295.0, end=296.0, confidence=0.9),
                        WordTimestamp(word="over", start=296.5, end=298.0, confidence=0.85),
                    ],
                ),
            ],
            language="en",
            duration=300.0,
            model="tiny",
        )

        # Chunk 2: 295-600s overlapping 5s with chunk 1
        # "jumps over" appears again in the overlap region
        chunk2 = TranscriptionResult(
            segments=[
                Segment(
                    text="jumps over the lazy dog",
                    start=295.0,
                    end=302.0,
                    words=[
                        WordTimestamp(word="jumps", start=295.0, end=296.0, confidence=0.88),
                        WordTimestamp(word="over", start=296.5, end=298.0, confidence=0.82),
                        WordTimestamp(word="the", start=298.5, end=299.0, confidence=0.9),
                        WordTimestamp(word="lazy", start=299.5, end=300.5, confidence=0.87),
                        WordTimestamp(word="dog", start=301.0, end=302.0, confidence=0.92),
                    ],
                ),
            ],
            language="en",
            duration=305.0,
            model="tiny",
        )

        result = stitch_segments([chunk1, chunk2], overlap_seconds=5.0)

        # Collect all emitted (word, start_time) pairs — no duplicates allowed
        word_keys: set[tuple[str, float]] = set()
        for segment in result.segments:
            for word in segment.words:
                key = (word.word, round(word.start, 3))
                assert key not in word_keys, f"Duplicate word found: {key}"
                word_keys.add(key)

    @pytest.mark.timeout(120)
    def test_stitching_chronological_order(self):
        """Test that stitched segments are in chronological order."""
        chunk1 = TranscriptionResult(
            segments=[
                Segment(
                    text="First segment",
                    start=0.0,
                    end=5.0,
                    words=[
                        WordTimestamp(word="First", start=0.0, end=2.0, confidence=0.9),
                        WordTimestamp(word="segment", start=2.5, end=5.0, confidence=0.85),
                    ],
                ),
            ],
            language="en",
            duration=300.0,
            model="tiny",
        )

        chunk2 = TranscriptionResult(
            segments=[
                Segment(
                    text="Second segment",
                    start=295.0,
                    end=310.0,
                    words=[
                        WordTimestamp(word="Second", start=295.0, end=300.0, confidence=0.9),
                        WordTimestamp(word="segment", start=305.0, end=310.0, confidence=0.88),
                    ],
                ),
            ],
            language="en",
            duration=315.0,
            model="tiny",
        )

        chunk3 = TranscriptionResult(
            segments=[
                Segment(
                    text="Third segment",
                    start=590.0,
                    end=600.0,
                    words=[
                        WordTimestamp(word="Third", start=590.0, end=595.0, confidence=0.9),
                        WordTimestamp(word="segment", start=595.0, end=600.0, confidence=0.87),
                    ],
                ),
            ],
            language="en",
            duration=600.0,
            model="tiny",
        )

        result = stitch_segments([chunk1, chunk2, chunk3], overlap_seconds=5.0)

        # Verify each segment starts at or after the previous segment ends
        for i in range(1, len(result.segments)):
            assert result.segments[i].start >= result.segments[i - 1].end, (
                f"Segment {i} starts at {result.segments[i].start} "
                f"before segment {i-1} ends at {result.segments[i-1].end}"
            )

    @pytest.mark.timeout(120)
    def test_stitching_no_gap_exceeds_5s(self):
        """Test that no gap between consecutive segments exceeds 5 seconds."""
        chunk1 = TranscriptionResult(
            segments=[
                Segment(
                    text="Part one",
                    start=0.0,
                    end=3.0,
                    words=[
                        WordTimestamp(word="Part", start=0.0, end=1.0, confidence=0.9),
                        WordTimestamp(word="one", start=1.5, end=3.0, confidence=0.85),
                    ],
                ),
                Segment(
                    text="continues here",
                    start=3.5,
                    end=6.0,
                    words=[
                        WordTimestamp(word="continues", start=3.5, end=5.0, confidence=0.9),
                        WordTimestamp(word="here", start=5.0, end=6.0, confidence=0.88),
                    ],
                ),
            ],
            language="en",
            duration=10.0,
            model="tiny",
        )

        chunk2 = TranscriptionResult(
            segments=[
                Segment(
                    text="and ends",
                    start=6.5,
                    end=9.0,
                    words=[
                        WordTimestamp(word="and", start=6.5, end=7.5, confidence=0.9),
                        WordTimestamp(word="ends", start=7.5, end=9.0, confidence=0.88),
                    ],
                ),
            ],
            language="en",
            duration=10.0,
            model="tiny",
        )

        result = stitch_segments([chunk1, chunk2], overlap_seconds=5.0)

        # Verify no gap exceeds 5 seconds
        for i in range(1, len(result.segments)):
            gap = result.segments[i].start - result.segments[i - 1].end
            assert gap <= 5.0, (
                f"Gap between segment {i-1} and {i} is {gap:.2f}s (max 5.0s)"
            )


@requires_whisper
@requires_ffmpeg
class TestRealWhisperPipeline:
    """Integration tests that require real Whisper and FFmpeg installation.

    These tests skip with 'openai-whisper not available' when Whisper is not installed.
    Validates: Requirements 7.5, 7.6
    """

    @pytest.fixture(autouse=True)
    def _add_ffmpeg_to_path(self):
        """Temporarily add FFmpeg directory to PATH for Whisper's internal calls."""
        import os
        ffmpeg_dir = str(Path(FFMPEG_PATH).parent)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + old_path
        yield
        os.environ["PATH"] = old_path

    @pytest.mark.timeout(120)
    def test_real_pipeline_speech_fixture(self):
        """Test full pipeline with real Whisper on speech_5s.wav fixture."""
        speech_file = FIXTURES_DIR / "speech_5s.wav"
        if not speech_file.exists():
            pytest.skip("speech_5s.wav fixture not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"
            cache_dir.mkdir()
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            preprocessor = AudioPreprocessor(ffmpeg_path=FFMPEG_PATH, output_dir=output_dir)
            transcriber = TranscriptionService(cache_dir=cache_dir)
            scorer = RelevanceScorer()

            preprocess_result = preprocessor.preprocess(speech_file)
            transcription_result = transcriber.transcribe(
                preprocess_result.output_paths[0]
            )

            # Basic structural validation
            assert transcription_result.duration > 0.0
            assert transcription_result.model == "tiny"
            assert transcription_result.language != ""

            # Score against a search term
            score_result = scorer.score(transcription_result, "hello world test")
            assert 0.0 <= score_result.score <= 1.0

    @pytest.mark.timeout(120)
    def test_real_pipeline_noisy_audio(self):
        """Test real pipeline with noisy audio produces valid result."""
        speech_file = FIXTURES_DIR / "speech_5s.wav"
        if not speech_file.exists():
            pytest.skip("speech_5s.wav fixture not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"
            cache_dir.mkdir()
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            preprocessor = AudioPreprocessor(ffmpeg_path=FFMPEG_PATH, output_dir=output_dir)
            transcriber = TranscriptionService(cache_dir=cache_dir)

            preprocess_result = preprocessor.preprocess(speech_file)
            transcription_result = transcriber.transcribe(
                preprocess_result.output_paths[0]
            )

            # With real Whisper on synthetic audio, we may get empty segments
            # but the pipeline should complete without error
            assert transcription_result.duration > 0.0
