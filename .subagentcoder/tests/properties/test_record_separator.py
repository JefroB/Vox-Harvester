# Feature: local-coder-workflow-improvements, Property 14: Record Separator Format
"""Property test: When multiple IssueRecords are logged sequentially, consecutive
record blocks (blocks containing '- **date:**') are separated by exactly the byte
sequence '\\n\\n---\\n\\n' — not more, not less.

**Validates: Requirements 6.3**
"""

import re
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueRecord, IssueLogger

# Strategy for simple alphanumeric text (no newlines)
_simple_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), whitelist_characters=" "),
    min_size=1,
    max_size=30,
).map(str.strip).filter(lambda s: len(s) > 0)

_issue_record_strategy = st.builds(
    IssueRecord,
    date=st.from_regex(r"2025-01-\d{2}T\d{2}:\d{2}:\d{2}", fullmatch=True),
    task_description=_simple_text,
    model_used=st.sampled_from(["qwen2.5-coder:7b", "qwen3-coder:30b"]),
    result=st.sampled_from(["success", "fail"]),
    tokens_generated=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    generation_speed=st.one_of(
        st.none(),
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    ),
    quality_notes=_simple_text,
    issues_found=st.lists(_simple_text, min_size=0, max_size=3),
    complexity_tier=st.sampled_from(["simple", "complex", "prose"]),
    review_iterations=st.integers(min_value=0, max_value=5),
)


@settings(max_examples=30)
@given(records=st.lists(_issue_record_strategy, min_size=2, max_size=5))
def test_record_separator_format(records: list) -> None:
    """Consecutive record blocks are separated by exactly '\\n\\n---\\n\\n'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        logger = IssueLogger(project_root)

        for record in records:
            logger.log_execution(record)

        content = logger.log_path.read_text(encoding="utf-8")

        # Find all positions where a record block starts (lines with '- **date:**')
        # Each record block starts at a '- **date:**' line
        record_starts = [m.start() for m in re.finditer(r"^- \*\*date:\*\*", content, re.MULTILINE)]

        assert len(record_starts) == len(records), (
            f"Expected {len(records)} record blocks, found {len(record_starts)}"
        )

        # For each pair of consecutive records, verify the separator between them
        separator = "\n\n---\n\n"
        for i in range(len(record_starts) - 1):
            # The region between current record start and next record start
            between = content[record_starts[i]:record_starts[i + 1]]
            # The separator should appear exactly once between consecutive records
            assert separator in between, (
                f"Expected separator '\\n\\n---\\n\\n' between record {i} and {i+1}, "
                f"but got: {repr(between[-20:])}"
            )
            # Verify separator appears exactly at the boundary (right before the next record)
            # The text just before the next record should end with the separator
            before_next = content[:record_starts[i + 1]]
            assert before_next.endswith(separator), (
                f"Record {i+1} is not immediately preceded by '\\n\\n---\\n\\n'. "
                f"Last 20 chars before: {repr(before_next[-20:])}"
            )
