# Feature: local-coder-workflow-improvements, Property 7: Append-Only Invariant
"""Property-based test for the append-only invariant of IssueLogger.

After appending a new IssueRecord via log_execution(), all previously-serialized
records MUST still be found byte-for-byte in the new file content (record content
is preserved; the summary section at the top may change).

**Validates: Requirements 3.5**
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueRecord, IssueLogger


# --- Strategies ---

# Safe alphabet: printable ASCII without newlines (newlines break field parsing)
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\n\r",
    ),
    min_size=1,
    max_size=50,
)

_issue_categories = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        blacklist_characters="\n\r",
    ),
    min_size=1,
    max_size=20,
)

_issue_record_strategy = st.builds(
    IssueRecord,
    date=st.from_regex(r"2023-0[1-9]-[012][0-9]T[012][0-9]:00:00Z", fullmatch=True),
    task_description=_safe_text,
    model_used=_safe_text,
    result=st.sampled_from(["success", "fail"]),
    tokens_generated=st.one_of(st.none(), st.integers(min_value=0, max_value=100000)),
    generation_speed=st.one_of(
        st.none(),
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ),
    quality_notes=_safe_text,
    issues_found=st.lists(_issue_categories, min_size=0, max_size=5),
    complexity_tier=st.sampled_from(["simple", "complex", "prose"]),
    review_iterations=st.integers(min_value=0, max_value=5),
)


@settings(max_examples=50)
@given(
    initial_records=st.lists(_issue_record_strategy, min_size=1, max_size=5),
    new_record=_issue_record_strategy,
)
def test_append_preserves_existing_records(
    initial_records: list,
    new_record: IssueRecord,
) -> None:
    """After appending a new record, all original records are still present byte-for-byte."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        project_root = Path(tmp_dir)
        logger = IssueLogger(project_root=project_root)

        # Write initial records one at a time so the file is in a valid state
        for record in initial_records:
            logger.log_execution(record)

        # Capture the serialized form of each initial record BEFORE the new append
        original_serialized = [
            logger._serialize_record(record) for record in initial_records
        ]

        # Append the new record
        logger.log_execution(new_record)

        # Read the final file content
        final_content = logger.log_path.read_text(encoding="utf-8")

        # Verify: each original record's serialized form is still present byte-for-byte
        for i, serialized in enumerate(original_serialized):
            assert serialized in final_content, (
                f"Original record {i} was NOT found byte-for-byte in final content.\n"
                f"Expected to find:\n{serialized!r}\n"
                f"In file content of length {len(final_content)}"
            )

        # Also verify the new record was appended
        new_serialized = logger._serialize_record(new_record)
        assert new_serialized in final_content, (
            "New record was not found in file after append."
        )
