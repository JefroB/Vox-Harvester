"""Pytest configuration for the audio validation test suite."""

import sys
from pathlib import Path

# Add src/ to the Python path so audio_validation package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
