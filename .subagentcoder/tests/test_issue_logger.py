from pathlib import Path

from local_coder.issue_logger import (
    IssueLogWriteError,
    IssueLogger,
    IssueRecord,
)


def test_log_file_created_with_heading(tmp_path: Path) -> None:
    """Test that the log file is created with the correct heading."""
    logger = IssueLogger(tmp_path)
    record = IssueRecord(
        date="2023-10-01T12:00:00Z",
        task_description="Test Task",
        model_used="test_model",
        result="success",
        tokens_generated=None,
        generation_speed=None,
        quality_notes="None",
        issues_found=[],
        complexity_tier="simple",
        review_iterations=0,
    )
    logger.log_execution(record)
    log_path = tmp_path / "docs" / "local-coder-issues.txt"
    assert log_path.exists()
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "# Local Coder Issues & Successes Log" in content


def test_docs_directory_created_when_absent(tmp_path: Path) -> None:
    """Test that the docs directory is created when it does not exist."""
    logger = IssueLogger(tmp_path / "nonexistent")
    record = IssueRecord(
        date="2023-10-01T12:00:00Z",
        task_description="Test Task",
        model_used="test_model",
        result="success",
        tokens_generated=None,
        generation_speed=None,
        quality_notes="None",
        issues_found=[],
        complexity_tier="simple",
        review_iterations=0,
    )
    logger.log_execution(record)
    assert (tmp_path / "nonexistent" / "docs").exists()


def test_issue_log_write_error_preserves_record() -> None:
    """Test that IssueLogWriteError preserves the record."""
    reason = "disk full"
    record = IssueRecord(
        date="2023-10-01T12:00:00Z",
        task_description="Test Task",
        model_used="test_model",
        result="success",
        tokens_generated=None,
        generation_speed=None,
        quality_notes="None",
        issues_found=[],
        complexity_tier="simple",
        review_iterations=0,
    )
    error = IssueLogWriteError(reason, record)
    assert error.reason == reason
    assert error.record is record


def test_tokens_field_fallback_when_unavailable(tmp_path: Path) -> None:
    """Test that '0 tokens in 0s' is used when no token data is available (Req 4.6)."""
    logger = IssueLogger(tmp_path)
    record = IssueRecord(
        date="2023-10-01T12:00:00Z",
        task_description="Test Task",
        model_used="test_model",
        result="success",
        tokens_generated=None,
        generation_speed=None,
        quality_notes="None",
        issues_found=[],
        complexity_tier="simple",
        review_iterations=0,
    )
    serialized = logger._serialize_record(record)
    assert "**tokens:** 0 tokens in 0s" in serialized


def test_serialized_record_parseable(tmp_path: Path) -> None:
    """Test that a serialized record can be parsed back to the original."""
    logger = IssueLogger(tmp_path)
    record = IssueRecord(
        date="2023-10-01T12:00:00Z",
        task_description="Test Task",
        model_used="test_model",
        result="success",
        tokens_generated=100,
        generation_speed=5.0,
        quality_notes="None",
        issues_found=["Issue 1", "Issue 2"],
        complexity_tier="simple",
        review_iterations=0,
    )
    serialized = logger._serialize_record(record)
    parsed_record = logger._parse_record(serialized)
    assert record.date == parsed_record.date
    assert record.task_description == parsed_record.task_description
    assert record.model_used == parsed_record.model_used
    assert record.result == parsed_record.result
    assert record.tokens_generated == parsed_record.tokens_generated
    assert record.generation_speed == parsed_record.generation_speed
    assert record.quality_notes == parsed_record.quality_notes
    assert record.issues_found == parsed_record.issues_found
    assert record.complexity_tier == parsed_record.complexity_tier
    assert record.review_iterations == parsed_record.review_iterations