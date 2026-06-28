"""Transcription service wrapping OpenAI Whisper for local speech-to-text.

Provides SHA-256 file caching, WAV validation, and timeout enforcement.
"""

import hashlib
import json
import tempfile
import threading
import wave
from pathlib import Path

from audio_validation.errors import (
    DependencyError,
    InvalidAudioError,
    TranscriptionTimeoutError,
)
from audio_validation.models import Segment, TranscriptionResult, WordTimestamp


class TranscriptionService:
    """Local Whisper-based speech-to-text with caching.

    Args:
        model_name: Whisper model size to use (default "tiny").
        cache_dir: Directory for storing cached transcription results.
            Defaults to a temp directory if not provided.
    """

    def __init__(self, model_name: str = "tiny", cache_dir: Path | None = None):
        self.model_name = model_name
        if cache_dir is None:
            self.cache_dir = Path(tempfile.gettempdir()) / "audio_transcription_cache"
        else:
            self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe a WAV file using Whisper.

        Validates input format, checks cache, runs inference with timeout.

        Args:
            audio_path: Path to a WAV audio file.

        Returns:
            TranscriptionResult with segments, language, duration, and model.

        Raises:
            InvalidAudioError: If file is not a valid WAV file.
            DependencyError: If openai-whisper is not installed.
            TranscriptionTimeoutError: If inference exceeds 120 seconds.
        """
        # 1. Validate input is a valid WAV file (without invoking Whisper)
        audio_duration = self._validate_wav(audio_path)

        # 2. Compute SHA-256 hash of file contents
        file_hash = self._compute_hash(audio_path)

        # 3. Check cache: return cached result if exists
        cache_file = self.cache_dir / f"{file_hash}.json"
        if cache_file.exists():
            return self._load_from_cache(cache_file)

        # 4. Check Whisper dependency availability
        self._check_whisper_available()

        # 5. Invoke Whisper with timeout
        import whisper

        result = self._run_whisper_with_timeout(whisper, audio_path)

        # 6. Parse Whisper output into TranscriptionResult
        transcription_result = self._parse_whisper_output(result, audio_duration)

        # 7. Cache result as JSON
        self._save_to_cache(cache_file, transcription_result)

        return transcription_result

    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hex digest of file bytes.

        Args:
            file_path: Path to file to hash.

        Returns:
            Hex string of SHA-256 digest.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _validate_wav(self, audio_path: Path) -> float:
        """Validate that audio_path is a readable WAV file.

        Args:
            audio_path: Path to validate.

        Returns:
            Duration of the WAV file in seconds.

        Raises:
            InvalidAudioError: If file cannot be opened as WAV.
        """
        try:
            with wave.open(str(audio_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate) if rate > 0 else 0.0
                return duration
        except Exception as e:
            raise InvalidAudioError(audio_path, str(e))

    def _check_whisper_available(self) -> None:
        """Check if openai-whisper can be imported.

        Raises:
            DependencyError: If whisper module is not importable.
        """
        import importlib.util

        spec = importlib.util.find_spec("whisper")
        if spec is None:
            raise DependencyError(
                "openai-whisper",
                "The 'whisper' package is not installed. "
                "Install with: pip install openai-whisper",
            )

    def _run_whisper_with_timeout(self, whisper_module, audio_path: Path) -> dict:
        """Run Whisper transcription with a 120-second timeout.

        Uses threading to enforce the timeout (Windows-compatible).

        Args:
            whisper_module: The imported whisper module.
            audio_path: Path to audio file.

        Returns:
            Whisper result dictionary.

        Raises:
            TranscriptionTimeoutError: If inference exceeds 120 seconds.
        """
        timeout_seconds = 120.0
        result_container: list = []
        error_container: list = []
        completed = threading.Event()

        def _inference():
            try:
                model = whisper_module.load_model(self.model_name)
                output = model.transcribe(str(audio_path), word_timestamps=True)
                result_container.append(output)
            except Exception as e:
                error_container.append(e)
            finally:
                completed.set()

        thread = threading.Thread(target=_inference, daemon=True)
        thread.start()
        finished = completed.wait(timeout=timeout_seconds)

        if not finished:
            raise TranscriptionTimeoutError(audio_path, timeout_seconds)

        if error_container:
            raise error_container[0]

        return result_container[0]

    def _parse_whisper_output(
        self, result: dict, wav_duration: float
    ) -> TranscriptionResult:
        """Parse Whisper output dict into TranscriptionResult.

        For silent audio (empty segments), returns empty segments list
        with duration from the WAV file.

        Args:
            result: Whisper output dictionary.
            wav_duration: Duration of original WAV file in seconds.

        Returns:
            Structured TranscriptionResult.
        """
        raw_segments = result.get("segments", [])

        # Silent audio: return empty segments with file duration
        if not raw_segments:
            return TranscriptionResult(
                segments=[],
                language=result.get("language", ""),
                duration=wav_duration,
                model=self.model_name,
            )

        segments = []
        for seg in raw_segments:
            words = []
            for w in seg.get("words", []):
                words.append(
                    WordTimestamp(
                        word=w.get("word", "").strip(),
                        start=float(w.get("start", 0.0)),
                        end=float(w.get("end", 0.0)),
                        confidence=float(w.get("probability", 0.0)),
                    )
                )
            segments.append(
                Segment(
                    text=seg.get("text", "").strip(),
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    words=words,
                )
            )

        duration = result.get("duration", wav_duration)
        if duration is None:
            duration = wav_duration

        return TranscriptionResult(
            segments=segments,
            language=result.get("language", ""),
            duration=float(duration),
            model=self.model_name,
        )

    def _load_from_cache(self, cache_file: Path) -> TranscriptionResult:
        """Load a TranscriptionResult from a JSON cache file.

        Args:
            cache_file: Path to the cache JSON file.

        Returns:
            Deserialized TranscriptionResult.
        """
        with open(cache_file, "r") as f:
            data = json.load(f)

        segments = []
        for seg_data in data.get("segments", []):
            words = []
            for w_data in seg_data.get("words", []):
                words.append(
                    WordTimestamp(
                        word=w_data["word"],
                        start=w_data["start"],
                        end=w_data["end"],
                        confidence=w_data["confidence"],
                    )
                )
            segments.append(
                Segment(
                    text=seg_data["text"],
                    start=seg_data["start"],
                    end=seg_data["end"],
                    words=words,
                )
            )

        return TranscriptionResult(
            segments=segments,
            language=data["language"],
            duration=data["duration"],
            model=data["model"],
        )

    def _save_to_cache(
        self, cache_file: Path, result: TranscriptionResult
    ) -> None:
        """Save a TranscriptionResult to a JSON cache file.

        Args:
            cache_file: Path to write the JSON file.
            result: TranscriptionResult to serialize.
        """
        data = {
            "segments": [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end,
                    "words": [
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence,
                        }
                        for w in seg.words
                    ],
                }
                for seg in result.segments
            ],
            "language": result.language,
            "duration": result.duration,
            "model": result.model,
        }
        with open(cache_file, "w") as f:
            json.dump(data, f)
