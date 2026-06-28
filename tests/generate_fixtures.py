"""Generate test audio fixtures for the e2e-audio-validation spec.

Creates:
- tests/fixtures/speech_5s.wav: 5-second 44.1kHz mono 16-bit WAV with
  multi-frequency sine wave tones simulating speech-like audio patterns
- tests/fixtures/silence.wav: 5-second silent WAV at 44.1kHz mono 16-bit
- tests/fixtures/corrupt.wav: file with random bytes (invalid WAV header)
- tests/fixtures/not_audio.txt: plain text file for format rejection tests
- tests/fixtures/expected_transcript.json: ground-truth TranscriptionResult JSON
"""

import json
import math
import os
import random
import struct
import wave
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_RATE = 44100
DURATION_SECONDS = 5
NUM_SAMPLES = SAMPLE_RATE * DURATION_SECONDS
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


def generate_speech_wav():
    """Generate a 5-second WAV with varying sine wave tones.

    Uses multiple frequency sweeps to simulate speech-like audio content.
    This won't contain actual speech but provides a valid audio file that
    the preprocessor and format conversion tests can exercise.
    """
    output_path = FIXTURES_DIR / "speech_5s.wav"

    # Generate multi-frequency audio to simulate speech patterns
    samples = []
    for i in range(NUM_SAMPLES):
        t = i / SAMPLE_RATE
        # Combine frequencies that vary over time to mimic speech formants
        # F1 range: 200-800 Hz, F2 range: 800-2500 Hz
        f1 = 300 + 200 * math.sin(2 * math.pi * 0.5 * t)  # slowly varying low freq
        f2 = 1500 + 500 * math.sin(2 * math.pi * 1.2 * t)  # mid freq variation
        f3 = 2800 + 300 * math.sin(2 * math.pi * 0.8 * t)  # higher formant

        # Amplitude modulation to simulate syllable rhythm (~4 Hz)
        envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 4.0 * t)

        # Mix the tones
        sample = envelope * (
            0.5 * math.sin(2 * math.pi * f1 * t)
            + 0.3 * math.sin(2 * math.pi * f2 * t)
            + 0.2 * math.sin(2 * math.pi * f3 * t)
        )

        # Scale to 16-bit range with some headroom
        sample_int = int(sample * 28000)
        sample_int = max(-32768, min(32767, sample_int))
        samples.append(sample_int)

    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        # Pack all samples as signed 16-bit little-endian
        frames = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(frames)

    print(f"Created {output_path} ({output_path.stat().st_size} bytes)")


def generate_silence_wav():
    """Generate a 5-second silent WAV at 44.1kHz mono 16-bit."""
    output_path = FIXTURES_DIR / "silence.wav"

    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        # All zero samples
        frames = struct.pack(f"<{NUM_SAMPLES}h", *([0] * NUM_SAMPLES))
        wf.writeframes(frames)

    print(f"Created {output_path} ({output_path.stat().st_size} bytes)")


def generate_corrupt_wav():
    """Generate a file with random bytes that don't form a valid WAV header."""
    output_path = FIXTURES_DIR / "corrupt.wav"

    # Write 512 random bytes - enough to not accidentally be valid
    random.seed(42)  # deterministic for reproducibility
    data = bytes(random.randint(0, 255) for _ in range(512))

    output_path.write_bytes(data)
    print(f"Created {output_path} ({output_path.stat().st_size} bytes)")


def generate_not_audio_txt():
    """Generate a plain text file for format rejection tests."""
    output_path = FIXTURES_DIR / "not_audio.txt"
    output_path.write_text("This is not an audio file.\n")
    print(f"Created {output_path} ({output_path.stat().st_size} bytes)")


def generate_expected_transcript_json():
    """Generate ground-truth TranscriptionResult JSON for speech_5s.wav.

    Since speech_5s.wav contains synthetic tones (not actual speech),
    this fixture represents the expected format and structure that a
    transcription would produce if the audio contained real speech.
    It's used for testing deserialization, round-trip, and comparison logic.
    """
    output_path = FIXTURES_DIR / "expected_transcript.json"

    transcript = {
        "segments": [
            {
                "text": "Hello world this is a test",
                "start": 0.0,
                "end": 2.5,
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.4, "confidence": 0.95},
                    {"word": "world", "start": 0.45, "end": 0.8, "confidence": 0.92},
                    {"word": "this", "start": 0.85, "end": 1.0, "confidence": 0.90},
                    {"word": "is", "start": 1.05, "end": 1.15, "confidence": 0.88},
                    {"word": "a", "start": 1.2, "end": 1.25, "confidence": 0.85},
                    {"word": "test", "start": 1.3, "end": 1.6, "confidence": 0.93},
                ],
            }
        ],
        "language": "en",
        "duration": 5.0,
        "model": "tiny",
    }

    output_path.write_text(json.dumps(transcript, indent=2) + "\n")
    print(f"Created {output_path} ({output_path.stat().st_size} bytes)")


def main():
    """Generate all test fixtures."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating fixtures in {FIXTURES_DIR}/\n")

    generate_speech_wav()
    generate_silence_wav()
    generate_corrupt_wav()
    generate_not_audio_txt()
    generate_expected_transcript_json()

    print("\nAll fixtures generated successfully.")


if __name__ == "__main__":
    main()
