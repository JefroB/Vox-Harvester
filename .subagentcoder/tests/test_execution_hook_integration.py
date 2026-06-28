"""Integration tests for the execution_hook module.

Tests end-to-end behavior of after_execution: verifying records
are written to the log file with correct fields based on various
execution outcomes.
"""

import pytest

from local_coder.execution_hook import after_execution


class TestSuccessfulExecutionWritesRecord:
    """Test that a successful execution writes a record to the log file."""

    def test_successful_execution_writes_record(self, tmp_path):
        """Call after_execution with exit_code=0 and a valid stats line.

        Verify it returns an IssueRecord with result='success',
        tokens_generated=500, generation_speed=50.0.
        Verify the log file exists at tmp_path/docs/local-coder-issues.txt.
        """
        record = after_execution(
            task_description="Generate helper utilities",
            stdout="Generated 500 tokens in 10s (50 tok/s)",
            stderr="",
            exit_code=0,
            model_used="qwen2.5-coder:7b",
            complexity_tier="simple",
            review_iterations=0,
            issues_detected=[],
            project_root=tmp_path,
        )

        assert record is not None
        assert record.result == "success"
        assert record.tokens_generated == 500
        assert record.generation_speed == 50.0
        assert record.review_iterations == 0

        log_file = tmp_path / "docs" / "local-coder-issues.txt"
        assert log_file.exists()

        content = log_file.read_text(encoding="utf-8")
        assert "success" in content
        assert "qwen2.5-coder:7b" in content


class TestTimeoutDetection:
    """Test that timeout is correctly recorded."""

    def test_timeout_detection(self, tmp_path):
        """Call with timeout=True, exit_code=0.

        Verify result='fail' and 'timeout' in record.issues_found.
        """
        record = after_execution(
            task_description="Long running task",
            stdout="",
            stderr="",
            exit_code=0,
            model_used="qwen2.5-coder:7b",
            complexity_tier="simple",
            review_iterations=0,
            issues_detected=[],
            timeout=True,
            project_root=tmp_path,
        )

        assert record is not None
        assert record.result == "fail"
        assert "timeout" in record.issues_found


class TestNonzeroExitRecordsCodeAndStderr:
    """Test that non-zero exit code records exit code and stderr."""

    def test_nonzero_exit_records_code_and_stderr(self, tmp_path):
        """Call with exit_code=1, stderr='some error'.

        Verify result='fail', 'exit_code:1' in issues_found,
        'some error' in issues_found.
        """
        record = after_execution(
            task_description="Failing task",
            stdout="",
            stderr="some error",
            exit_code=1,
            model_used="qwen2.5-coder:7b",
            complexity_tier="simple",
            review_iterations=0,
            issues_detected=[],
            project_root=tmp_path,
        )

        assert record is not None
        assert record.result == "fail"
        assert "exit_code:1" in record.issues_found
        assert "some error" in record.issues_found


class TestReviewIterationCapping:
    """Test that review iterations are capped at 5."""

    def test_review_iteration_capping(self, tmp_path):
        """Call with review_iterations=7.

        Verify record.review_iterations==5, result='fail',
        'abandoned' in issues_found.
        """
        record = after_execution(
            task_description="Complex task with many iterations",
            stdout="Generated 200 tokens in 5s (40 tok/s)",
            stderr="",
            exit_code=0,
            model_used="qwen2.5-coder:7b",
            complexity_tier="complex",
            review_iterations=7,
            issues_detected=[],
            project_root=tmp_path,
        )

        assert record is not None
        assert record.review_iterations == 5
        assert record.result == "fail"
        assert "abandoned" in record.issues_found


class TestStderrTruncationAt200:
    """Test that stderr is truncated at 200 characters."""

    def test_stderr_truncation_at_200(self, tmp_path):
        """Call with exit_code=1, stderr='x'*500.

        Verify the stderr in issues_found is exactly 200 chars.
        """
        long_stderr = "x" * 500
        record = after_execution(
            task_description="Task with long stderr",
            stdout="",
            stderr=long_stderr,
            exit_code=1,
            model_used="qwen2.5-coder:7b",
            complexity_tier="simple",
            review_iterations=0,
            issues_detected=[],
            project_root=tmp_path,
        )

        assert record is not None
        assert record.result == "fail"
        assert "exit_code:1" in record.issues_found

        # Find the stderr entry (not the exit_code entry)
        stderr_entries = [
            issue for issue in record.issues_found if issue != "exit_code:1"
        ]
        assert len(stderr_entries) == 1
        assert len(stderr_entries[0]) == 200
        assert stderr_entries[0] == "x" * 200
