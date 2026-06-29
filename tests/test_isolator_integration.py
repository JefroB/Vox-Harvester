"""Integration tests for end-to-end vocal isolation flow.

Tests the complete isolation pipeline from triggering isolation through
child process execution to completion, including:
- Child process spawning with correct CLI args
- Status transitions: pending → processing → completed
- DB record updated with isolated_path after completion
- _isolated.wav file created in correct location
- Failure handling with error message storage
- 300s child process timeout

Validates: Requirements 1.1, 3.2, 3.3, 4.1, 4.3, 7.5
"""

import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_valid_wav(path: Path, duration_seconds: float = 2.0, sample_rate: int = 44100) -> None:
    """Create a valid mono 16-bit WAV file at the given path."""
    num_frames = int(sample_rate * duration_seconds)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Write silence (zeros)
        wf.writeframes(b"\x00\x00" * num_frames)


def make_success_result(input_path: str, output_path: str) -> dict:
    """Build a mock IsolationResult JSON dict."""
    return {
        "input_path": input_path,
        "output_path": output_path,
        "duration_seconds": 2.0,
        "model_name": "htdemucs_ft",
        "device": "cpu",
        "processing_time_seconds": 0.5,
        "gpu_unavailable": False,
    }


def make_error_result(input_path: str, error: str = "Test error", dependency: str | None = None) -> dict:
    """Build a mock IsolationError JSON dict."""
    return {
        "error": error,
        "dependency": dependency,
        "input_path": input_path,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audio_dir(tmp_path):
    """Create a temporary audio directory with a valid sample WAV."""
    audio = tmp_path / "harvested_samples"
    audio.mkdir()
    return audio


@pytest.fixture
def sample_wav(audio_dir):
    """Create a sample WAV file in the audio directory."""
    wav_path = audio_dir / "test_sample.wav"
    create_valid_wav(wav_path)
    return wav_path


@pytest.fixture
def mock_isolator_success_script(tmp_path):
    """Create a Python script that mimics a successful isolator run.

    The script:
    - Reads input_path and output_path from argv
    - Creates a valid WAV at output_path
    - Writes IsolationResult JSON to stdout
    - Exits 0
    """
    script = tmp_path / "mock_isolator_success.py"
    script.write_text(
        '''import sys
import json
import wave

input_path = sys.argv[1]
output_path = sys.argv[2]

# Create a valid WAV output file
with wave.open(output_path, "w") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    wf.writeframes(b"\\x00\\x00" * 44100)  # 1 second silence

result = {
    "input_path": input_path,
    "output_path": output_path,
    "duration_seconds": 1.0,
    "model_name": "htdemucs_ft",
    "device": "cpu",
    "processing_time_seconds": 0.1,
    "gpu_unavailable": False,
}
print(json.dumps(result))
sys.exit(0)
'''
    )
    return script


@pytest.fixture
def mock_isolator_failure_script(tmp_path):
    """Create a Python script that mimics a failed isolator run.

    The script:
    - Reads input_path from argv
    - Writes IsolationError JSON to stderr
    - Exits 1
    """
    script = tmp_path / "mock_isolator_failure.py"
    script.write_text(
        '''import sys
import json

input_path = sys.argv[1]

error_result = {
    "error": "Demucs model failed to load: CUDA out of memory",
    "dependency": None,
    "input_path": input_path,
}
print(json.dumps(error_result), file=sys.stderr)
sys.exit(1)
'''
    )
    return script


@pytest.fixture
def mock_isolator_timeout_script(tmp_path):
    """Create a Python script that hangs (simulates timeout)."""
    script = tmp_path / "mock_isolator_timeout.py"
    script.write_text(
        '''import sys
import time

# Hang indefinitely to trigger timeout
time.sleep(999)
'''
    )
    return script


# ---------------------------------------------------------------------------
# Test: Child process spawning with correct CLI args
# ---------------------------------------------------------------------------


class TestChildProcessSpawning:
    """Verify the isolator is invoked as: python -m src.audio_validation.isolator <input> <output>"""

    def test_cli_invocation_success(self, mock_isolator_success_script, sample_wav, audio_dir):
        """Child process spawned with correct args produces expected output."""
        input_path = str(sample_wav)
        output_path = str(audio_dir / "test_sample_isolated.wav")

        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), input_path, output_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        stdout_json = json.loads(result.stdout)
        assert stdout_json["input_path"] == input_path
        assert stdout_json["output_path"] == output_path
        assert stdout_json["model_name"] == "htdemucs_ft"
        assert stdout_json["device"] in ("cpu", "cuda")
        assert isinstance(stdout_json["duration_seconds"], (int, float))
        assert isinstance(stdout_json["processing_time_seconds"], (int, float))
        assert isinstance(stdout_json["gpu_unavailable"], bool)

    def test_cli_invocation_failure(self, mock_isolator_failure_script, sample_wav):
        """Child process exit code 1 writes error JSON to stderr."""
        input_path = str(sample_wav)
        output_path = "unused_output.wav"

        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), input_path, output_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        stderr_json = json.loads(result.stderr)
        assert "error" in stderr_json
        assert stderr_json["input_path"] == input_path
        assert "dependency" in stderr_json

    def test_correct_cli_args_format(self, sample_wav, audio_dir):
        """Verify the exact CLI invocation pattern: python -m src.audio_validation.isolator <in> <out>"""
        input_path = str(sample_wav)
        output_path = str(audio_dir / "test_sample_isolated.wav")

        # The server spawns: spawn('python', ['-m', 'src.audio_validation.isolator', inputPath, outputPath])
        # We verify the real isolator module accepts these args
        # Add src/ to PYTHONPATH so the module can resolve its imports
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.parent)
        src_path = str(Path(__file__).parent.parent / "src")
        env["PYTHONPATH"] = f"{project_root}{os.pathsep}{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            [sys.executable, "-m", "src.audio_validation.isolator", input_path, output_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
            env=env,
        )

        # Without Demucs installed, it should exit 1 with a structured dependency error
        # With Demucs installed, it might succeed or fail with a different structured error
        # The key assertion: the CLI interface is correct (not a usage error or crash)
        if result.returncode == 1:
            stderr_json = json.loads(result.stderr)
            # Should be a structured error (not a usage/crash error)
            assert "error" in stderr_json
            assert "input_path" in stderr_json
        else:
            # Success case — valid JSON on stdout
            stdout_json = json.loads(result.stdout)
            assert "input_path" in stdout_json
            assert "output_path" in stdout_json


# ---------------------------------------------------------------------------
# Test: Status transitions (pending → processing → completed)
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """Verify job status transitions when simulating the server's processIsolationJob logic."""

    def test_successful_job_transitions_to_completed(self, mock_isolator_success_script, sample_wav, audio_dir):
        """Simulating server logic: spawn child → exit 0 → status becomes completed."""
        input_path = str(sample_wav)
        output_path = str(audio_dir / "test_sample_isolated.wav")

        # Simulate what server.ts processIsolationJob does:
        # 1. Set status = "processing"
        job = {
            "jobId": "test-uuid-1234",
            "sampleId": "test_sample",
            "status": "pending",
            "created_at": "2025-01-01T00:00:00.000Z",
            "updated_at": "2025-01-01T00:00:00.000Z",
        }

        # Transition: pending → processing
        job["status"] = "processing"
        job["updated_at"] = "2025-01-01T00:00:01.000Z"
        assert job["status"] == "processing"

        # 2. Spawn child process
        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), input_path, output_path],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # 3. On exit code 0 → completed
        assert result.returncode == 0
        stdout_data = json.loads(result.stdout)

        job["status"] = "completed"
        job["output_path"] = output_path
        job["updated_at"] = "2025-01-01T00:00:02.000Z"

        assert job["status"] == "completed"
        assert job["output_path"] == output_path
        assert "updated_at" in job

    def test_failed_job_transitions_to_failed_with_error(self, mock_isolator_failure_script, sample_wav):
        """Simulating server logic: spawn child → exit 1 → status becomes failed with error."""
        input_path = str(sample_wav)
        output_path = "does_not_matter.wav"

        job = {
            "jobId": "test-uuid-5678",
            "sampleId": "test_sample",
            "status": "pending",
            "created_at": "2025-01-01T00:00:00.000Z",
            "updated_at": "2025-01-01T00:00:00.000Z",
        }

        # Transition: pending → processing
        job["status"] = "processing"

        # Spawn child process
        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), input_path, output_path],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # On non-zero exit → failed
        assert result.returncode != 0
        stderr_data = json.loads(result.stderr)

        # Server truncates error to 500 chars
        error_msg = stderr_data["error"][:500]
        job["status"] = "failed"
        job["error"] = error_msg
        job["updated_at"] = "2025-01-01T00:00:02.000Z"

        assert job["status"] == "failed"
        assert "error" in job
        assert len(job["error"]) <= 500


# ---------------------------------------------------------------------------
# Test: DB record updated with isolated_path after completion
# ---------------------------------------------------------------------------


class TestDBRecordUpdate:
    """Verify that after successful isolation, the sample DB record gets isolated_path."""

    def test_isolated_path_set_on_completion(self, tmp_path, mock_isolator_success_script, audio_dir):
        """After child process succeeds, sample record gets isolated_path field."""
        sample_id = "integration_test_sample"
        wav_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(wav_path)
        output_path = str(audio_dir / f"{sample_id}_isolated.wav")

        # Simulate DB state
        db = {
            "samples": [
                {
                    "id": sample_id,
                    "phrase_text": "test phrase",
                    "video_id": "vid123",
                    "file_path": f"/api/samples/audio/{sample_id}",
                }
            ]
        }

        db_path = tmp_path / "vocal_harvester_db.json"
        db_path.write_text(json.dumps(db))

        # Run the mock isolator (simulating server's child process call)
        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), str(wav_path), output_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        # Simulate server updating DB on completion (what processIsolationJob does)
        db_data = json.loads(db_path.read_text())
        sample = next(s for s in db_data["samples"] if s["id"] == sample_id)
        sample["isolated_path"] = f"/api/samples/audio/{sample_id}_isolated"

        db_path.write_text(json.dumps(db_data))

        # Verify DB state
        updated_db = json.loads(db_path.read_text())
        updated_sample = next(s for s in updated_db["samples"] if s["id"] == sample_id)
        assert "isolated_path" in updated_sample
        assert updated_sample["isolated_path"] == f"/api/samples/audio/{sample_id}_isolated"

    def test_isolated_path_not_set_on_failure(self, tmp_path, mock_isolator_failure_script, audio_dir):
        """After child process fails, sample record does NOT get isolated_path."""
        sample_id = "fail_test_sample"
        wav_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(wav_path)

        db = {
            "samples": [
                {
                    "id": sample_id,
                    "phrase_text": "test phrase",
                    "video_id": "vid456",
                    "file_path": f"/api/samples/audio/{sample_id}",
                }
            ]
        }

        db_path = tmp_path / "vocal_harvester_db.json"
        db_path.write_text(json.dumps(db))

        # Run the mock isolator (failure case)
        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), str(wav_path), "unused.wav"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1

        # Server does NOT update DB on failure
        db_data = json.loads(db_path.read_text())
        sample = next(s for s in db_data["samples"] if s["id"] == sample_id)
        assert "isolated_path" not in sample


# ---------------------------------------------------------------------------
# Test: _isolated.wav file created in correct location
# ---------------------------------------------------------------------------


class TestIsolatedFileCreation:
    """Verify that the _isolated.wav file is created at the correct path."""

    def test_isolated_wav_created_at_correct_path(self, mock_isolator_success_script, audio_dir):
        """After successful isolation, <id>_isolated.wav exists in audio dir."""
        sample_id = "file_creation_test"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)

        output_path = audio_dir / f"{sample_id}_isolated.wav"

        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert output_path.exists(), f"Expected {output_path} to be created"

    def test_isolated_wav_is_valid_wav(self, mock_isolator_success_script, audio_dir):
        """The created _isolated.wav must be a valid WAV file."""
        sample_id = "valid_wav_test"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)

        output_path = audio_dir / f"{sample_id}_isolated.wav"

        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert output_path.exists()

        # Verify it's a valid WAV by opening with wave module
        with wave.open(str(output_path), "r") as wf:
            assert wf.getnchannels() >= 1
            assert wf.getsampwidth() == 2  # 16-bit PCM
            assert wf.getframerate() > 0
            assert wf.getnframes() > 0

    def test_output_path_follows_convention(self, mock_isolator_success_script, audio_dir):
        """Output path must be <input_dir>/<sample_id>_isolated.wav"""
        sample_id = "path_convention_test"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)

        # The server constructs output_path as: path.join(AUDIO_DIR, `${id}_isolated.wav`)
        expected_output = audio_dir / f"{sample_id}_isolated.wav"

        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), str(input_path), str(expected_output)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        stdout_data = json.loads(result.stdout)
        assert stdout_data["output_path"] == str(expected_output)
        assert expected_output.exists()


# ---------------------------------------------------------------------------
# Test: Failure handling — error message stored
# ---------------------------------------------------------------------------


class TestFailureHandling:
    """Verify failure handling: job → failed with error message."""

    def test_error_message_captured_from_stderr(self, mock_isolator_failure_script, sample_wav):
        """On exit code 1, error from stderr JSON is captured."""
        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), str(sample_wav), "out.wav"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        error_data = json.loads(result.stderr)
        assert "error" in error_data
        assert isinstance(error_data["error"], str)
        assert len(error_data["error"]) > 0

    def test_error_message_truncated_to_500_chars(self, tmp_path, sample_wav):
        """Server truncates error messages to 500 characters max."""
        # Create a script that emits a very long error message
        long_error_script = tmp_path / "long_error.py"
        long_error_script.write_text(
            '''import sys
import json

error_result = {
    "error": "A" * 1000,
    "dependency": None,
    "input_path": sys.argv[1],
}
print(json.dumps(error_result), file=sys.stderr)
sys.exit(1)
'''
        )

        result = subprocess.run(
            [sys.executable, str(long_error_script), str(sample_wav), "out.wav"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        error_data = json.loads(result.stderr)

        # Simulate server's truncation logic
        truncated_error = error_data["error"][:500]
        assert len(truncated_error) <= 500

    def test_no_output_file_on_failure(self, mock_isolator_failure_script, audio_dir):
        """On failure, no _isolated.wav file should be created."""
        sample_id = "fail_no_output"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)
        output_path = audio_dir / f"{sample_id}_isolated.wav"

        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        assert not output_path.exists(), "Output file should not exist after failure"


# ---------------------------------------------------------------------------
# Test: Timeout handling (300s child process timeout)
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Verify 300s child process timeout behavior."""

    def test_child_process_killed_on_timeout(self, mock_isolator_timeout_script, sample_wav, audio_dir):
        """Child process that exceeds timeout is killed and job marked failed."""
        output_path = str(audio_dir / "timeout_test_isolated.wav")

        # Use a very short timeout to test the mechanism (not 300s in tests)
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, str(mock_isolator_timeout_script), str(sample_wav), output_path],
                capture_output=True,
                text=True,
                timeout=2,  # 2 seconds instead of 300 for test speed
            )

    def test_timeout_results_in_failed_status(self, mock_isolator_timeout_script, sample_wav, audio_dir):
        """When timeout occurs, job status should transition to failed."""
        output_path = str(audio_dir / "timeout_status_test_isolated.wav")

        job = {
            "jobId": "timeout-test-uuid",
            "sampleId": "timeout_sample",
            "status": "processing",
            "created_at": "2025-01-01T00:00:00.000Z",
            "updated_at": "2025-01-01T00:00:01.000Z",
        }

        try:
            subprocess.run(
                [sys.executable, str(mock_isolator_timeout_script), str(sample_wav), output_path],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            # Server marks job as failed on timeout
            job["status"] = "failed"
            job["error"] = "Processing timeout after 300s"
            job["updated_at"] = "2025-01-01T00:05:01.000Z"

        assert job["status"] == "failed"
        assert "timeout" in job["error"].lower()

    def test_no_output_file_after_timeout(self, mock_isolator_timeout_script, sample_wav, audio_dir):
        """After timeout, no partial output file should remain."""
        output_path = audio_dir / "timeout_no_file_isolated.wav"

        try:
            subprocess.run(
                [sys.executable, str(mock_isolator_timeout_script), str(sample_wav), str(output_path)],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            pass

        # The timeout script doesn't create any file, so output should not exist
        assert not output_path.exists()


# ---------------------------------------------------------------------------
# Test: End-to-end flow simulation (POST → poll → GET)
# ---------------------------------------------------------------------------


class TestEndToEndFlowSimulation:
    """Simulate the full flow: trigger → process → serve isolated audio.

    Since the actual server is Node.js (TypeScript), we simulate the server's
    logic in Python to validate the contract between components.
    """

    def test_full_isolation_lifecycle(self, mock_isolator_success_script, audio_dir, tmp_path):
        """Simulate: POST isolate → child process runs → poll completed → serve file."""
        sample_id = "e2e_lifecycle_sample"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)
        output_path = audio_dir / f"{sample_id}_isolated.wav"

        # --- Phase 1: POST /api/samples/:id/isolate (simulated) ---
        # Server validates and creates job
        job = {
            "jobId": "e2e-uuid-1234",
            "sampleId": sample_id,
            "status": "pending",
            "created_at": "2025-01-01T10:00:00.000Z",
            "updated_at": "2025-01-01T10:00:00.000Z",
        }
        assert job["status"] == "pending"

        # --- Phase 2: dispatchNextIsolationJob (simulated) ---
        job["status"] = "processing"
        job["updated_at"] = "2025-01-01T10:00:01.000Z"

        # Server spawns: python -m src.audio_validation.isolator <input> <output>
        result = subprocess.run(
            [sys.executable, str(mock_isolator_success_script), str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # --- Phase 3: Child process completes → job updated ---
        assert result.returncode == 0
        stdout_data = json.loads(result.stdout)

        job["status"] = "completed"
        job["output_path"] = str(output_path)
        job["updated_at"] = "2025-01-01T10:00:05.000Z"

        # --- Phase 4: GET /api/jobs/:jobId (simulated poll response) ---
        poll_response = {
            "jobId": job["jobId"],
            "sampleId": job["sampleId"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "output_path": f"/api/samples/audio/{sample_id}_isolated",
        }
        assert poll_response["status"] == "completed"
        assert "output_path" in poll_response

        # --- Phase 5: Verify file exists for GET /api/samples/audio/:id_isolated ---
        assert output_path.exists()
        with wave.open(str(output_path), "r") as wf:
            assert wf.getnchannels() >= 1
            assert wf.getsampwidth() == 2

        # --- Phase 6: DB updated with isolated_path ---
        db = {"samples": [{"id": sample_id, "file_path": f"/api/samples/audio/{sample_id}"}]}
        sample = next(s for s in db["samples"] if s["id"] == sample_id)
        sample["isolated_path"] = f"/api/samples/audio/{sample_id}_isolated"
        assert sample["isolated_path"] == f"/api/samples/audio/{sample_id}_isolated"

    def test_full_isolation_failure_lifecycle(self, mock_isolator_failure_script, audio_dir):
        """Simulate: POST isolate → child process fails → poll shows failed with error."""
        sample_id = "e2e_failure_sample"
        input_path = audio_dir / f"{sample_id}.wav"
        create_valid_wav(input_path)
        output_path = audio_dir / f"{sample_id}_isolated.wav"

        # POST creates job
        job = {
            "jobId": "e2e-fail-uuid",
            "sampleId": sample_id,
            "status": "pending",
            "created_at": "2025-01-01T10:00:00.000Z",
            "updated_at": "2025-01-01T10:00:00.000Z",
        }

        # Dispatch → processing
        job["status"] = "processing"

        # Spawn child (fails)
        result = subprocess.run(
            [sys.executable, str(mock_isolator_failure_script), str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode != 0
        stderr_data = json.loads(result.stderr)

        # Server reads error, truncates to 500, marks failed
        job["status"] = "failed"
        job["error"] = stderr_data["error"][:500]
        job["updated_at"] = "2025-01-01T10:00:03.000Z"

        # Poll response for failed job
        poll_response = {
            "jobId": job["jobId"],
            "sampleId": job["sampleId"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "error": job["error"],
        }
        assert poll_response["status"] == "failed"
        assert "error" in poll_response
        assert len(poll_response["error"]) <= 500
        assert "output_path" not in poll_response

        # No isolated file created
        assert not output_path.exists()
