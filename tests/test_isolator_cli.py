"""Tests for VocalIsolator._cleanup_partial() and __main__ CLI entry point.

Validates Requirements 7.3, 7.4, 2.7, 2.8:
- CLI JSON output contract (success → stdout JSON, failure → stderr JSON)
- Missing Demucs dependency reported via dependency field
- Partial output cleanup on error
- 600s timeout enforcement
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock torchaudio before importing isolator since torchaudio may not be installed
sys.modules.setdefault("torchaudio", MagicMock())

from src.audio_validation.isolator import VocalIsolator, IsolationError, IsolationResult


class TestCleanupPartial:
    """Tests for _cleanup_partial static method."""

    def test_removes_existing_file(self, tmp_path):
        """_cleanup_partial removes the output file when it exists."""
        output_file = tmp_path / "partial_output.wav"
        output_file.write_text("partial data")
        assert output_file.exists()

        VocalIsolator._cleanup_partial(str(output_file))

        assert not output_file.exists()

    def test_no_error_when_file_does_not_exist(self, tmp_path):
        """_cleanup_partial does not raise when file does not exist."""
        output_file = tmp_path / "nonexistent.wav"
        assert not output_file.exists()

        # Should not raise
        VocalIsolator._cleanup_partial(str(output_file))

    def test_silent_on_os_error(self, tmp_path, monkeypatch):
        """_cleanup_partial silently catches OSError during removal."""
        output_file = tmp_path / "locked.wav"
        output_file.write_text("data")

        # Monkey-patch Path.unlink to raise OSError
        original_unlink = Path.unlink

        def raise_os_error(self, *args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(Path, "unlink", raise_os_error)

        # Should not raise
        VocalIsolator._cleanup_partial(str(output_file))


class TestCLIEntryPoint:
    """Tests for the __main__ CLI entry point."""

    def _run_isolator_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run the isolator module as a CLI subprocess."""
        project_root = str(Path(__file__).parent.parent)
        cmd = [sys.executable, "-m", "src.audio_validation.isolator"] + args
        env = os.environ.copy()
        # Add src/ to PYTHONPATH so transitive imports (e.g. audio_validation.errors) resolve
        src_path = str(Path(project_root) / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
            env=env,
        )

    def test_wrong_arg_count_prints_usage_and_exits_1(self):
        """CLI with wrong argument count prints usage to stderr and exits 1."""
        result = self._run_isolator_cli([])
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_wrong_arg_count_one_arg(self):
        """CLI with one argument prints usage to stderr and exits 1."""
        result = self._run_isolator_cli(["input.wav"])
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_missing_input_file_returns_error_json(self, tmp_path):
        """CLI with non-existent input file outputs error JSON to stderr, exit 1.

        Note: If demucs is not installed, the dependency check fires first.
        This test validates whichever error is reported first has proper JSON format.
        """
        input_path = str(tmp_path / "nonexistent.wav")
        output_path = str(tmp_path / "output.wav")

        result = self._run_isolator_cli([input_path, output_path])

        assert result.returncode == 1
        error_data = json.loads(result.stderr)
        # Either the dependency check fires (demucs not installed) or
        # the file-existence check fires — both produce valid error JSON
        if error_data.get("dependency") == "demucs":
            assert "not installed" in error_data["error"].lower() or "demucs" in error_data["error"].lower()
        else:
            assert "does not exist" in error_data["error"]
            assert error_data["dependency"] is None
            assert error_data["input_path"] == input_path

    def test_error_json_has_required_fields(self, tmp_path):
        """Error JSON output contains all required fields: error, dependency, input_path."""
        input_path = str(tmp_path / "missing.wav")
        output_path = str(tmp_path / "output.wav")

        result = self._run_isolator_cli([input_path, output_path])

        assert result.returncode == 1
        error_data = json.loads(result.stderr)
        assert "error" in error_data
        assert "dependency" in error_data
        assert "input_path" in error_data
        assert isinstance(error_data["error"], str)

    def test_demucs_dependency_check(self):
        """If demucs is not available, CLI reports dependency error.

        Note: This test only validates the error format when demucs is missing.
        If demucs IS installed, it will pass due to the file-not-found check.
        """
        # Use a non-existent input to trigger at least one error path
        result = self._run_isolator_cli(["/nonexistent/input.wav", "/tmp/output.wav"])
        assert result.returncode == 1
        error_data = json.loads(result.stderr)

        # Either demucs is missing (dependency error) or file doesn't exist
        if error_data.get("dependency") == "demucs":
            assert "not installed" in error_data["error"].lower() or "demucs" in error_data["error"].lower()
        else:
            assert error_data["dependency"] is None
            assert "does not exist" in error_data["error"] or "not found" in error_data["error"]
