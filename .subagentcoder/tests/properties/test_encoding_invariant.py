# Feature: local-coder-workflow-improvements, Property 13: File Encoding Invariant
"""Property test: For any IssueRecord containing Unicode text (emoji, CJK, RTL characters)
in task_description and quality_notes, the written file SHALL be valid UTF-8 without BOM
and SHALL use only LF line endings.

**Validates: Requirements 6.2**
"""

import tempfile
from datetime import datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueRecord, IssueLogger


def _sanitize(s: str) -> str:
    """Replace newlines with spaces and remove '**' sequences to avoid breaking markdown."""
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("**", "")
    return s


# Strategy for Unicode text including emoji, CJK, and RTL characters
_unicode_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        whitelist_characters="\U0001f600\U0001f4a5\U0001f680\u4e16\u754c\u0627\u0644\u0639",
    ),
    min_size=1,
    max_size=150,
)


@settings(max_examples=50)
@given(
    task_description=_unicode_text,
    quality_notes=_unicode_text,
)
def test_file_encoding_invariant(task_description: str, quality_notes: str) -> None:
    """Written file is valid UTF-8 without BOM and uses LF line endings."""
    task_description = _sanitize(task_description)
    quality_notes = _sanitize(quality_notes)

    record = IssueRecord(
        date=datetime.now().isoformat(timespec="seconds"),
        task_description=task_description,
        model_used="test-model",
        result="success",
        tokens_generated=100,
        generation_speed=50.0,
        quality_notes=quality_notes,
        issues_found=[],
        complexity_tier="simple",
        review_iterations=0,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger = IssueLogger(project_root=tmp_path)
        logger.log_execution(record)

        log_file = tmp_path / "docs" / "local-coder-issues.txt"
        assert log_file.exists(), "Log file was not created"

        # Read as raw bytes for encoding checks
        raw_bytes = log_file.read_bytes()

        # Verify: first 3 bytes are NOT the UTF-8 BOM
        assert raw_bytes[:3] != b"\xef\xbb\xbf", "File starts with UTF-8 BOM"

        # Verify: bytes decode as valid UTF-8
        raw_bytes.decode("utf-8")  # Raises UnicodeDecodeError if invalid

        # Verify: no CRLF line endings — only LF
        assert b"\r\n" not in raw_bytes, "File contains CRLF line endings"
