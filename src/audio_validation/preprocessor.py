"""Audio preprocessing utilities for the validation subsystem.

Provides FFmpeg-based conversion of audio files to Whisper-compatible
16kHz mono 16-bit PCM WAV format, with chunking for long files.
"""

import subprocess
import tempfile
from pathlib import Path

from .errors import PreprocessError
from .models import PreprocessResult

# Maximum chunk duration in seconds before segmentation is triggered.
MAX_CHUNK_SECONDS = 300
# Overlap in seconds between consecutive chunks.
OVERLAP_SECONDS = 5


class AudioPreprocessor:
    """Converts harvested audio files to Whisper-compatible format.

    Uses FFmpeg/ffprobe subprocesses to validate, probe, and transcode
    audio into 16kHz mono 16-bit PCM WAV. Files longer than 300 seconds
    are segmented into overlapping chunks.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", output_dir: Path | None = None):
        """Initialise the preprocessor.

        :param ffmpeg_path: Path or name of the ffmpeg binary (ffprobe is
            derived by replacing 'ffmpeg' with 'ffprobe' in this path).
        :param output_dir: Directory for output files. If None, a persistent
            temp directory is created.
        """
        self.ffmpeg_path = ffmpeg_path
        # Derive ffprobe path from ffmpeg path.
        self._ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if output_dir is not None:
            self.output_dir = output_dir
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._tmp_dir = tempfile.mkdtemp(prefix="audio_preprocess_")
            self.output_dir = Path(self._tmp_dir)

    def preprocess(self, source_path: Path) -> PreprocessResult:
        """Convert source audio to 16kHz mono 16-bit PCM WAV.

        For files ≤300 s a single output file is produced. For files >300 s
        the audio is segmented into chunks of at most 300 s with 5 s overlap
        between adjacent chunks.

        :param source_path: Path to the source audio file.
        :return: PreprocessResult with output paths and format metadata.
        :raises PreprocessError: If the source does not exist, is not
            decodable audio, or FFmpeg fails.
        """
        # 1. Validate source file exists.
        if not source_path.exists():
            raise PreprocessError("Source file does not exist", source_path)

        # 2. Validate source is decodable audio via ffprobe.
        duration = self._probe_duration(source_path)

        # 3. Convert based on duration.
        if duration <= MAX_CHUNK_SECONDS:
            output_path = self._convert_single(source_path)
            output_paths = [output_path]
        else:
            output_paths = self._convert_chunked(source_path, duration)

        return PreprocessResult(
            output_paths=output_paths,
            sample_rate=16000,
            channels=1,
            bit_depth=16,
            duration_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _probe_duration(self, source_path: Path) -> float:
        """Use ffprobe to validate the file and retrieve its duration.

        :raises PreprocessError: If the file cannot be decoded or duration
            cannot be determined.
        """
        cmd = [
            self._ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise PreprocessError(
                "ffprobe not found; ensure FFmpeg is installed", source_path
            )
        except subprocess.TimeoutExpired:
            raise PreprocessError(
                "ffprobe timed out while probing file", source_path
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise PreprocessError(
                f"Source file could not be decoded: {stderr}", source_path
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise PreprocessError(
                "Source file could not be decoded: no duration reported",
                source_path,
            )

        try:
            duration = float(stdout)
        except ValueError:
            raise PreprocessError(
                f"Could not parse duration from ffprobe output: {stdout!r}",
                source_path,
            )

        return duration

    def _convert_single(self, source_path: Path) -> Path:
        """Convert a single file to 16kHz mono 16-bit PCM WAV."""
        output_path = self.output_dir / f"{source_path.stem}_preprocessed.wav"
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(source_path),
            "-ar", "16000",
            "-ac", "1",
            "-sample_fmt", "s16",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            raise PreprocessError(
                f"FFmpeg conversion failed: {exc.stderr.strip()}", source_path
            )
        except subprocess.TimeoutExpired:
            raise PreprocessError("FFmpeg conversion timed out", source_path)

        return output_path

    def _convert_chunked(self, source_path: Path, total_duration: float) -> list[Path]:
        """Segment a long file into ≤300 s chunks with 5 s overlap.

        Chunk N starts at N * (MAX_CHUNK_SECONDS - OVERLAP_SECONDS).
        Uses -ss (start) and -t (duration) FFmpeg flags per chunk.
        """
        output_paths: list[Path] = []
        step = MAX_CHUNK_SECONDS - OVERLAP_SECONDS  # 295 s between chunk starts
        chunk_index = 0
        start_time = 0.0

        while start_time < total_duration:
            # Duration of this chunk (may be shorter for the last chunk).
            chunk_len = min(MAX_CHUNK_SECONDS, total_duration - start_time)

            output_path = (
                self.output_dir / f"{source_path.stem}_chunk_{chunk_index:03d}.wav"
            )
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss", f"{start_time:.3f}",
                "-i", str(source_path),
                "-t", f"{chunk_len:.3f}",
                "-ar", "16000",
                "-ac", "1",
                "-sample_fmt", "s16",
                str(output_path),
            ]
            try:
                subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=120
                )
            except subprocess.CalledProcessError as exc:
                raise PreprocessError(
                    f"FFmpeg chunking failed at chunk {chunk_index}: "
                    f"{exc.stderr.strip()}",
                    source_path,
                )
            except subprocess.TimeoutExpired:
                raise PreprocessError(
                    f"FFmpeg chunking timed out at chunk {chunk_index}",
                    source_path,
                )

            output_paths.append(output_path)
            start_time += step
            chunk_index += 1

        return output_paths