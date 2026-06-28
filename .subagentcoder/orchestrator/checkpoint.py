"""Inline checkpoint executor for the orchestrator.

Executes test/validation commands directly without spawning a subagent.
Handles timeout enforcement, output truncation, and command validation.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


# Constants
CHECKPOINT_TIMEOUT_SECONDS = 300
MAX_OUTPUT_LINES = 200


@dataclass
class CheckpointResult:
    """Result of a checkpoint command execution.

    Attributes:
        success: True if command exited with code 0.
        exit_code: The process exit code, or None if command was invalid/not run.
        duration_seconds: Wall-clock execution time in seconds.
        output: Combined stdout/stderr, truncated to the last 200 lines.
        error_message: Human-readable error description on failure, None on success.
    """

    success: bool
    exit_code: int | None
    duration_seconds: float
    output: str
    error_message: str | None


def _truncate_output(output: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    """Keep only the last `max_lines` lines of output.

    Args:
        output: The full combined stdout/stderr text.
        max_lines: Maximum number of lines to retain (default 200).

    Returns:
        The last `max_lines` lines joined by newline, or the full output
        if it has fewer lines.
    """
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(lines[-max_lines:])


def run_checkpoint(command: str | None, project_root: Path) -> CheckpointResult:
    """Execute a checkpoint command and return the result.

    Validates the command, runs it as a shell process in `project_root`,
    enforces a 300-second timeout, and truncates output to the last 200 lines.

    Args:
        command: The shell command to execute. Must be non-empty, non-whitespace.
        project_root: The directory in which to execute the command.

    Returns:
        CheckpointResult indicating success/failure with details.
    """
    # Validate command: None, empty, or whitespace-only → immediate failure
    if command is None or not command.strip():
        return CheckpointResult(
            success=False,
            exit_code=None,
            duration_seconds=0.0,
            output="",
            error_message="[ERROR] checkpoint: Invalid command — missing, empty, or whitespace-only.",
        )

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=CHECKPOINT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start_time
        # Collect whatever output was produced before timeout
        raw_output = ""
        if exc.stdout:
            raw_output += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode(errors="replace")
        if exc.stderr:
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode(errors="replace")
            raw_output += stderr_text

        return CheckpointResult(
            success=False,
            exit_code=None,
            duration_seconds=duration,
            output=_truncate_output(raw_output),
            error_message=(
                f"[ERROR] checkpoint: Command exceeded {CHECKPOINT_TIMEOUT_SECONDS}s "
                f"timeout and was killed."
            ),
        )

    duration = time.monotonic() - start_time

    # Combine stdout and stderr
    combined_output = result.stdout + result.stderr
    truncated_output = _truncate_output(combined_output)

    if result.returncode == 0:
        return CheckpointResult(
            success=True,
            exit_code=0,
            duration_seconds=duration,
            output=truncated_output,
            error_message=None,
        )
    else:
        return CheckpointResult(
            success=False,
            exit_code=result.returncode,
            duration_seconds=duration,
            output=truncated_output,
            error_message=(
                f"[ERROR] checkpoint: Command exited with code {result.returncode}."
            ),
        )
